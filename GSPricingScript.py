import re
import time
import json
import logging
import random
from datetime import datetime
import mysql.connector
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.options import Options
from seleniumwire import webdriver
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from undetected_chromedriver import ChromeOptions
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from modules.runTimeSecrets import HOST, DB, USER, PASS, HOST2, DB2, USER2, PASS2, HOST3, DB3, USER3, PASS3
from modules.saveRanks import commence as evalRanking

def loggerInit(logFileName):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s:%(name)s:%(message)s')
    file_handler = logging.FileHandler(f'logs/{logFileName}')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)
    logger.addHandler(stream_handler)
    return logger
logger = loggerInit(logFileName="pricing.log")

def get_text(main_div, selector):
    try:
        if not selector:
            return ""
        return main_div.find_element(By.CSS_SELECTOR, selector).text.strip()
    except Exception:
        return ""


def clean_code(value: str):
    if not value:
        return ""

    value = value.upper().strip()

    # remove labels safely
    value = re.sub(r'(SKU:|MODEL #|MODEL:)', '', value)

    # remove vendor prefix only
    value = re.sub(r'^K-', '', value)

    return value.strip()

def tokenize(value: str):
    value = clean_code(value)
    return value.split('-')

def is_strict_match(sku, mpn):
    return tokenize(sku) == tokenize(mpn)    

def normalize_code(val):
    if not val:
        return ""
    
    val = val.strip().upper()
    # remove K- prefix (safe + flexible spacing)
    val = re.sub(r"^K-\s*", "", val)
    return val

def normalize_brand(brand):
    if not brand:
        return None

    brand = brand.lower().replace(".", "").replace(" ", "").strip()

    # Brands to be treated as AO Smith
    aosmith_aliases = {
        "aosmith",
        "lochinvar",
        "waterheaterparts",
        "aosmith&lochinvar",
        "lochinvar&aosmith",
    }

    if brand in aosmith_aliases:
        return "aosmith"

    return brand

def scraped_by_mpn(driver,vendor_id, vendor_url, product_id, brand_name_from_DB, mpn, product_url, vendor_product_id):
    try:
        setAsProcessed(product_id, vendor_id, atmpt=1)
    
        temp2 = {}

        driver.get(product_url)
        time.sleep(2)

        logger.info(f"Product URL: {product_url}")
        # with open("soup.html", "w", encoding="utf-8") as f:
        #     f.write(driver.page_source)

        try:
            MainDiv = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'main.wrapper.main-content')))
        except:
            print("Main Div NOT Found :")
            MainDiv = None
        if MainDiv:   
            try:
                mpn_element = driver.find_element(By.CSS_SELECTOR, 'meta[itemprop="mpn"]')
                sku = mpn_element.get_attribute("content").strip()
                
            except Exception as e:
                print("MPN not found:")
                sku = None

        if sku and mpn and sku.lower() == mpn.lower():
            mpn = sku
        else:
            logger.info(f"SKU '{sku}' does not match MPN '{mpn}' ")
            return None, None        

        if sku is None:
            return None, None

        try:
            brand_el = driver.find_element(By.CSS_SELECTOR, 'p.product-meta[itemprop="brand"]')
            brand_text = (brand_el.text or brand_el.get_attribute("textContent") or '').strip()
        except Exception as e:
            print("brand not found:", e)
            brand_text = None

        brand_name = normalize_brand(brand_text)
        db_brand = normalize_brand(brand_name_from_DB)

        print(brand_name)
        print(db_brand)

        if not db_brand or not brand_name:
            return None, None

        if db_brand != brand_name:
            logger.debug("Brands are not matched")
            return None, None

        try:
            msrp_el = driver.find_element(By.CSS_SELECTOR, 'div.product-view div.product__price div.ComparePrice strike')
            # print(msrp_el)
            msrp = msrp_el.text.strip().replace("$", "").replace("£", "").replace(",", "").replace("Was", "").replace("Regular price", "").strip()
        except:
            msrp = None
        print(msrp)

        try:
            price_el = driver.find_element(By.CSS_SELECTOR, 'span#productPrice-product-template span.visually-hidden')
            # print(price_el)
            price = price_el.text.strip().replace("$", "").replace("£", "").replace(",", "").strip()
        except:
            price = None
        print(price)

        vendorprice_isbackorder = 'no'
        stock_text = None
        try:
            stock_text_element = driver.find_element(By.CSS_SELECTOR, 
                'div.grid div.grid-item div.EasyStock-Text div.EasyStock-Text-Title')
            stock_text= stock_text_element.text.strip().lower()
        except:
            stock_text = None
                
        if stock_text:
            if 'back order' in stock_text:
                vendorprice_isbackorder  = 'yes'
            elif 'in stock' in stock_text:
                stock_text = 'In Stock'
            elif 'out of stock' in stock_text:
                stock_text = 'Out Of Stock'
                
        qty = None
        vendorprice_stock = None
        try:
            el = driver.find_element(By.CSS_SELECTOR, 'div.EasyStock-Text[data-easystock-x-qty]')
            qty = int(el.get_attribute("data-easystock-x-qty"))
            vendorprice_stock = qty
        except Exception as e:
            print("stock qty not found:")

        def set_input(driver, by, locator, value):
            element = driver.find_element(by, locator)

            current = (element.get_attribute("value") or "").strip()

            if current == value:
                return

            element.click()
            element.send_keys(Keys.CONTROL, "a")
            element.send_keys(Keys.DELETE)
            element.send_keys(value)


        def set_select(driver, by, locator, text):
            select = Select(driver.find_element(by, locator))
            if select.first_selected_option.text.strip() != text:
                select.select_by_visible_text(text)

        try:               
            wait = WebDriverWait(driver, 10)
            # Click Add to Cart
            add_to_cart = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button#addToCart")
                )
            )

            driver.execute_script("arguments[0].click();", add_to_cart)
            logger.debug("Add to Cart button clicked")

            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[type="checkbox"]')))
            time.sleep(5)

            # Wait for Calculate Shipping button after AJAX update
            shipping_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="checkbox"]')))
            driver.execute_script("arguments[0].click();", shipping_button)
            logger.debug("Shipping button clicked")
            time.sleep(2)

            check_out = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button[name="checkout"]')))
            driver.execute_script("arguments[0].click();", check_out)
            logger.debug("checkout button clicked")
            time.sleep(2)

            wait = WebDriverWait(driver, 30)

            # Email
            wait.until(EC.visibility_of_element_located((By.ID, "email")))

            set_input(driver, By.ID, "email", "test@example.com")
            set_input(driver, By.NAME, "firstName", "John")
            set_input(driver, By.NAME, "lastName", "Doe")
            set_input(driver, By.NAME, "address1", "123 Main Street")
            set_input(driver, By.NAME, "city", "New York")
            set_input(driver, By.NAME, "postalCode", "11001")
            set_input(driver, By.NAME, "phone", "5165551234")

            set_select(driver, By.NAME, "countryCode", "United States")
            set_select(driver, By.NAME, "zone", "New York")

            update_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]')))
            driver.execute_script("arguments[0].click();", update_button)
            # Wait for page/ajax update
            wait.until(EC.staleness_of(update_button))
            # Find it again
            update_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]')))
            driver.execute_script("arguments[0].click();", update_button)

            try:
                shipping_element = wait.until(
                    EC.visibility_of_element_located((
                        By.XPATH,
                        '//*[@id="CustomProperties-P0-0"]/div/div[1]/div[1]/div/div/div[2]/div/aside/div/div/section/div/section/div[2]/div[2]/div[2]/div[2]/span[2]'
                    ))
                )

                shipping_text = shipping_element.text
                print("Shipping text:", shipping_text)

                shipping_cost = float(shipping_text.replace("$", "").replace(",", "").strip())

            except Exception as e:
                logger.exception("Failed to get shipping")
                shipping_cost = None

            if shipping_cost is None:
                shipping_cost = 0.0

            price = float(str(price).replace("$", "").replace(",", "").strip())
            final_price = round(price + shipping_cost, 2)
            print(final_price)

            logger.debug(f"Shipping: {shipping_cost}")
            time.sleep(2)

            driver.get('https://www.gsistore.com/cart')
            time.sleep(2)

            remove_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.icon-fallback-text.btn-secondary.remove")))
            driver.execute_script("arguments[0].click();", remove_button)
            logger.debug("Product removed from cart")

        except Exception as e:
            logger.exception(f"Error finding or clicking button: {e}")
                

        temp2["vendorprice_price"] = price
        temp2["vendorprice_finalprice"] = final_price
        temp2['vendorprice_shipping'] = shipping_cost
        temp2['vendorprice_isbackorder'] = vendorprice_isbackorder
        temp2["product_page_price"] = None
        temp2["In_cart_price"] = "0"
        temp2["msrp"] = msrp
        temp2["vendorprice_stock_text"] = stock_text
        temp2["vendorprice_stock"] = vendorprice_stock
        temp2["vendor_call_for_best_price"] = "0"
        temp2["scraped_by_system"] = "Preeti pc"
        temp2["source"] = "direct_from_website"
        temp2["product_condition"] = "New"

        print("PRICE:", temp2)
        print("------------------------------------------------")#5070707, 5070709

        # product_id, vendor_product_id = insertIntoMsp(temp, vendor_id)
        price_text = temp2.get('vendorprice_price')
        if isinstance(price_text, str):
            price_lower = price_text.lower().strip()
            if re.search(r'\b(best price|price unavailable|call for best price|none)\b', price_lower):
                temp2['vendorprice_price'] = '0.0'
                temp2['vendorprice_finalprice'] = '0.0'
                temp2['product_page_price'] = '0.0'
                temp2['In_cart_price'] = '0'
                temp2['vendor_call_for_best_price'] = '1'
            else:
                temp2['vendor_call_for_best_price'] = '0'
        else:
            temp2['vendor_call_for_best_price'] = '0'

        insertall(product_id, vendor_product_id, temp2, vendor_id)
        evalRanking(vendor_id, product_id)
        setAsScraped(product_id, vendor_id, atmpt=1)

    except Exception as e:
        logger.debug(f"Error in scraped_by_mpn(): {e}")
        return None, None
    
def VendorWebsiteScrapingMPNStatus(product_mpn, vendor_id, product_id):
    dateTime = getDatetime()   
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            checkProductVendorURLQuery = "SELECT product_id FROM VendorWebsiteScrapingMPNStatus WHERE product_id = %s AND vendor_id = %s"
            this.execute(checkProductVendorURLQuery, [product_id,vendor_id])
            records = this.fetchall()
            if len(records) == 0:
                insertProductVendorURLQuery = "INSERT INTO VendorWebsiteScrapingMPNStatus (product_id, product_mpn, vendor_id, product_status, product_checking_date) VALUES (%s, %s, %s, %s, %s)"
                this.execute(insertProductVendorURLQuery, [product_id, product_mpn, vendor_id, '0', dateTime])
                conn.commit()
                logger.info(f'Mpn not found our site "{product_mpn}"')
            else:
                updateProductVendorURLQuery = """UPDATE VendorWebsiteScrapingMPNStatus SET product_status = %s, product_mpn = %s , product_checking_date = %s WHERE product_id = %s AND vendor_id = %s"""
                this.execute(updateProductVendorURLQuery, ['0', product_mpn, dateTime, product_id, vendor_id])
                conn.commit()
                logger.info(f'{vendor_id} >> Updated product VendorWebsiteScrapingMPNStatus for product_id "{product_id}".')
    except mysql.connector.Error as e:
        logger.warning(f"{vendor_id} >> MySQL ERROR VendorWebsiteScrapingMPNStatus() >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

def saveNotValidReason(Not_Valid_Reason, vendor_product_id):
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            this.execute("UPDATE ProductVendor SET Valid_for_Direct_Website_Scraping = %s, Not_Valid_for_Direct_Website_Scraping_Reason = %s WHERE vendor_product_id = %s", ("0", Not_Valid_Reason, vendor_product_id))
            conn.commit()
            # print(f"Record Updated for product_id ({product_id}).")
            logger.info(f"Not Valid Reason Updated for vendor_product_id ({vendor_product_id}).")
    except mysql.connector.Error as e:
        logger.warning(f"{vendor_product_id} >> MySQL ERROR saveNotValidReason() >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

def setAsProcessed(product_id, vendor_id, atmpt=1):
    """
    Marking product as scraped
    """
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor()
            this.execute("UPDATE ProductVendor SET is_processed_for_direct_scraping = %s WHERE product_id = %s AND vendor_id = %s;", ('1', product_id, vendor_id))
            conn.commit()
            logger.debug(f"Product (ID: {product_id}) is marked as processed")
    except mysql.connector.Error as e:
        if 'timeout' in str(e):
            if atmpt == 3:
                logger.error(f"MySQL ERROR setAsProcessed(3/3) >> {e}")
            else:
                logger.error(f"Retrying to set product as processed ({atmpt+1}/3)")
                setAsProcessed(product_id, atmpt=atmpt+1)
        else:
            logger.error(f"MySQL ERROR setAsProcessed() >> {e}")
    finally:
        if conn.is_connected():
            this.close()
            conn.close()

def setAsScraped(product_id, vendor_id, atmpt=1):
    """
    Marking product as scraped
    """
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor()
            this.execute("UPDATE ProductVendor SET is_scraped_for_direct_scraping = %s WHERE product_id = %s AND vendor_id = %s;", ('1', product_id, vendor_id))
            conn.commit()
            logger.debug(f"Product (ID: {product_id}) is marked as scraped")
    except mysql.connector.Error as e:
        if 'timeout' in str(e):
            if atmpt == 3:
                logger.error(f"MySQL ERROR setAsScraped(3/3) >> {e}")
            else:
                logger.error(f"Retrying to set product as scraped ({atmpt+1}/3)")
                setAsScraped(product_id, atmpt=atmpt+1)
        else:
            logger.error(f"MySQL ERROR setAsScraped() >> {e}")
    finally:
        if conn.is_connected():
            this.close()
            conn.close()


def insertIntoMsp(row, vendor_id):
    product_id = vendor_product_id = None  # Initialize to None  product_pdfs
    try:
        brand_id = checkInsertBrand(vendor_id, row['brand_name'])
        product_id = checkInsertProduct(vendor_id, brand_id, row['product_mpn'], row['product_name'], row['msrp'], row['product_image'], row['product_pdfs'])
        vendor_product_id = checkInsertProductVendor(vendor_id, product_id, row['vendor_sku'], row['product_name'], row['product_url'], row['msrp'])
        checkInsertProductVendorURL(vendor_id, vendor_product_id, row['product_url'])
    except Exception as e:
        logger.error(f"Error in insertIntoMsp: {e}")
    return product_id, vendor_product_id

def getBrandRawName(brand_name):
    letters, numbers, spaces = [], [], []
    for character in brand_name:
        if character.isalpha():
            letters.append(character)
        elif character.isnumeric():
            numbers.append(character)
        elif character.isspace():
            spaces.append(character)
    if len(letters) > 0: raw_name = "".join(spaces + letters)
    else: raw_name = "".join(spaces + numbers)
    return raw_name

# Add brand if doesn't exists
def checkInsertBrand(vendor_id,brand_name):
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            this.execute("SELECT brand_id FROM BrandSynonyms WHERE brand_synonym = %s", (brand_name,))
            brand_id = this.fetchone()
            if brand_id:
                logger.info(f"{vendor_id} >> Found brand synonym: {brand_name} ({brand_id[0]})")
                return brand_id[0]
            else:
                brandRawNname = getBrandRawName(brand_name)
                brandRaw = brandRawNname.lower().strip()
                this.execute("SELECT brand_id, brand_name FROM Brand WHERE brand_raw_name = %s",(brandRaw,))
                records = this.fetchone()
                if records:
                    fetchedBrandId = records[0]
                    fetchedBrandName = records[1]
                    if fetchedBrandName != brand_name:
                        insertBrandSynonymsQuery = "INSERT INTO BrandSynonyms (brand_id,brand_synonym) VALUES (%s,%s);"
                        this.execute(insertBrandSynonymsQuery,(fetchedBrandId,brand_name))
                        conn.commit()
                        logger.info(f"Inserted {brandRawNname} as a synonym for {fetchedBrandName}.")
                    else:
                        logger.info(f"{brandRaw} Brand Name Matched")
                        return fetchedBrandId
                else:
                    insertBrandQuery = "INSERT INTO Brand (brand_name,brand_key,brand_raw_name) VALUES (%s,%s,%s);"
                    this.execute(insertBrandQuery,(brand_name,brand_name.replace(" ", "-").lower(),brandRaw))
                    conn.commit()
                    logger.info(f'{vendor_id} >> Added new brand "{brand_name} ({this.lastrowid})".')
                    return this.lastrowid
    except mysql.connector.Error as e:
        logger.warning(f"{vendor_id} >> MySQL ERROR checkInsertBrand() >> {e}")
        logger.warning(f"{vendor_id}, {brand_name}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

# Add product if doesn't exists
def checkInsertProduct(vendor_id, brand_id, mpn, name, msrp, image,product_pdfs):
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)

            # Check if product exists
            checkProductQuery = "SELECT product_id, product_name, product_image FROM Product WHERE brand_id = %s AND product_mpn = %s"
            this.execute(checkProductQuery, [brand_id, mpn])
            records = this.fetchone()

            if records is None:
                if msrp != '':
                    insertProductQuery = """INSERT INTO Product (brand_id, product_name, product_mpn, msrp, product_image,product_pdfs) VALUES (%s, %s, %s, %s, %s, %s)"""
                    this.execute(insertProductQuery, (brand_id, name, mpn, msrp, image,product_pdfs))
                else:
                    insertProductQuery = """INSERT INTO Product (brand_id, product_name, product_mpn, product_image,product_pdfs) VALUES (%s, %s, %s, %s, %s)"""
                    this.execute(insertProductQuery, (brand_id, name, mpn, image, product_pdfs))
                conn.commit()
                logger.info(f'{vendor_id} >> Added new product with mpn "{mpn} ({this.lastrowid})".')
                return this.lastrowid
            else:
                product_id, product_name, product_image = records
                if product_name is None:
                    this.execute("UPDATE Product SET product_name = %s WHERE product_id = %s", [name, product_id])
                # if not product_image or "afsupply" not in product_image.lower():
                #     this.execute("UPDATE Product SET product_image = %s WHERE product_id = %s", [image, product_id])
                if msrp != '':
                    this.execute("UPDATE Product SET msrp = %s WHERE product_id = %s AND msrp IS NULL", [msrp, product_id])
                conn.commit()
                logger.info(f'{vendor_id} >> Updated details for product with mpn "{mpn} ({product_id})".')
                return product_id
    except mysql.connector.Error as e:
        logger.warning(f"{vendor_id} >> MySQL ERROR checkInsertProduct() >> {e}")
        logger.warning(f"{vendor_id}, {brand_id}, {mpn}, {name}, {msrp}, {image}")
        return None
    finally:
        if conn.is_connected():
            this.close()
            conn.close()

# Add product vendor if doesn't exists
def checkInsertProductVendor(vendor_id, product_id, sku, name, product_url, msrp):
    try:
        # First check if we have valid input
        if product_id is None:
            logger.warning(f"{vendor_id} >> Cannot insert vendor product: product_id is None")
            return None
            
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            if msrp == '' or msrp is None:
                msrp = None  # or set to 0.0 if you prefer a default value

            checkProductVendorQuery = "SELECT vendor_product_id, product_name FROM ProductVendor WHERE vendor_id = %s AND product_id = %s LIMIT 1"
            this.execute(checkProductVendorQuery, [vendor_id, product_id])
            records = this.fetchone()
            
            # Handle case where no records found
            if records is None:
                # Insert new record
                insertProductVendorQuery = "INSERT INTO ProductVendor (vendor_id, product_id, product_name, vendor_sku, msrp) VALUES (%s, %s, %s, %s, %s)"
                this.execute(insertProductVendorQuery, (vendor_id, product_id, name, sku, msrp))
                conn.commit()
                logger.info(f'{vendor_id} >> Added new product in ProductVendor "{vendor_id} x {product_id}".')
                return this.lastrowid
            else:
                # Update existing record
                # vp_id = int(records[0])
                vp_id, product_name = records
                if product_name == None:
                    this.execute("Update ProductVendor SET product_name = %s WHERE vendor_product_id = %s",[product_name,vp_id])
                updateProductDetailQuery = "UPDATE ProductVendor SET vendor_sku = %s, msrp = %s WHERE vendor_product_id = %s"
                this.execute(updateProductDetailQuery, [sku, msrp, vp_id])
                conn.commit()
                if this.rowcount == 1:
                    logger.info(f'{vendor_id} >> Updated details for vendor_product_id ({vp_id}).')
                logger.info(f'{vendor_id} >> Returned vendor_product_id ({vp_id}).')
                return vp_id
    except mysql.connector.Error as e:
        logger.error(f"{vendor_id} >> MySQL ERROR checkInsertProductVendor() >> {e}")
        return None
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

# Add product vendor url if doesn't exists
def checkInsertProductVendorURL(vendor_id, vendor_product_id, product_url):
    # url = product_url.split('&')[0]
    url = product_url
    print("vendor_url:",url)
    print("vendor_raw_url:",product_url)
    try:
        if not vendor_product_id:
            logger.warning(f"{vendor_id} >> Invalid vendor_product_id: {vendor_product_id}")
            return  # Exit the function early
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            checkProductVendorURLQuery = "SELECT vendor_product_id FROM VendorURL WHERE vendor_product_id = %s"
            this.execute(checkProductVendorURLQuery, [vendor_product_id,])
            records = this.fetchall()
            if len(records) == 0:
                insertProductVendorURLQuery = "INSERT INTO VendorURL (vendor_product_id, vendor_raw_url, vendor_url) VALUES (%s, %s, %s)"
                this.execute(insertProductVendorURLQuery, [vendor_product_id, product_url, url])
                conn.commit()
                logger.info(f'{vendor_id} >> Added product vendor URL for vendor_product_id "{vendor_product_id}".')
                return this.lastrowid
            else:
                # fatchquary = "SELECT vendor_url_id, vendor_raw_url, vendor_url FROM VendorURL WHERE vendor_product_id = %s"
                # this.execute(fatchquary, [vendor_product_id])
                # results = this.fetchall()
                # if results[0][2] != url:
                # Update the existing record
                updateProductVendorURLQuery = """UPDATE VendorURL SET vendor_raw_url = %s, vendor_url = %s WHERE vendor_product_id = %s"""
                this.execute(updateProductVendorURLQuery, [product_url, url, vendor_product_id])
                conn.commit()
                logger.info(f'{vendor_id} >> Updated product vendor URL for vendor_product_id "{vendor_product_id}".')
                # else:
                #     logger.info(f'{vendor_id} >> Same Product vendor URL already exists for vendor_product_id "{vendor_product_id}".')
                # try:
                #     vendor_url_id, vendor_raw_url, vendor_url = results[0][0], results[0][1], results[0][2]
                #     checkProductVendorURLQuery = "SELECT vendor_bakup_url_id FROM BuilddotcomeDirectScraping_VendorURLBackup WHERE vendor_product_id = %s"
                #     this.execute(checkProductVendorURLQuery, [vendor_product_id,])
                #     Record = this.fetchone()
                #     if Record is None or len(Record) == 0:
                #         insertProductVendorURLQuery = "INSERT INTO BuilddotcomeDirectScraping_VendorURLBackup (vendor_url_id, vendor_product_id, vendor_raw_url, vendor_url) VALUES (%s, %s, %s, %s)"
                #         this.execute(insertProductVendorURLQuery, [vendor_url_id, vendor_product_id, vendor_raw_url, vendor_url])
                #         conn.commit()
                #         logger.info(f'Added product vendor_url for vendor_product_id "{vendor_product_id}" for vendor_bakup_url_id {this.lastrowid}.')
                #     else:
                #         if Record[0] is not None:
                #             fatchquary = "SELECT vendor_url_id, vendor_raw_url, vendor_url FROM BuilddotcomeDirectScraping_VendorURLBackup WHERE vendor_bakup_url_id = %s"
                #             this.execute(fatchquary, [Record[0],])
                #             Records = this.fetchone()
                #             if Records and Records[2] != vendor_url:
                #                 # Update the existing record
                #                 updateProductVendorURLQuery = """UPDATE BuilddotcomeDirectScraping_VendorURLBackup SET vendor_raw_url = %s, vendor_url = %s WHERE vendor_bakup_url_id = %s"""
                #                 this.execute(updateProductVendorURLQuery, [vendor_raw_url, vendor_url, Record[0]])
                #                 conn.commit()
                #                 logger.info(f'Updated vendor_raw_url, vendor_url for vendor_bakup_url_id "{Record[0]}".')
                #             else:
                #                 logger.info(f'Same Product vendor URL already exists for vendor_bakup_url_id "{Record[0]}".')
                # except mysql.connector.Error as e:
                #     logger.warning(f"MySQL ERROR checkInsertProductVendorURL() >> {e}")
                # results.append(Records)
    except mysql.connector.Error as e:
        logger.warning(f"{vendor_id} >> MySQL ERROR checkInsertProductVendorURL() >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

# call all function into this function
def insertall(product_id, vendor_product_id, temp, vendor_id):
    try:
        price = temp['vendorprice_price']
        price_str = str(price).strip() if price is not None else ''
        
        if price_str != '':
            vendorTempPricing(vendor_product_id, temp)
            rpVendorPricingHistory(vendor_product_id, temp, vendor_id)
            # productMsrpUpdate(product_id, temp)
            # productVendorMsrpUpdate(vendor_product_id, temp)
        else:
            logger.info(f"Invalid price value: {price}")
            
    except Exception as e:
        logger.error(f"Error in insertall(): {e}")

def getDatetime():
    currentDatetime = datetime.now()
    return currentDatetime.strftime("%Y-%m-%d %H:%M:%S")

# Temp vnendor pricing data
def vendorTempPricing(vendor_product_id, temp):
    dateTime = getDatetime()
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            checkQuery = "SELECT vendor_product_id FROM TempVendorPricing WHERE vendor_product_id = %s AND source = %s LIMIT 1"
            this.execute(checkQuery, (vendor_product_id, temp['source']))
            records = this.fetchone()
            if records:
                getPricequary = "SELECT * FROM TempVendorPricing WHERE vendor_product_id = %s AND source = 'direct_from_website'"
                this.execute(getPricequary, (records[0],))
                result = this.fetchone()
                savedprice = str(result[2]).strip()
                scrapedprice = str(temp['vendorprice_price']).strip()
                if savedprice == scrapedprice:
                    logger.info(f"Same vendor price already exists for vendor_product_id {vendor_product_id}")
                else:
                    updateQuery = """UPDATE TempVendorPricing SET is_price_changed = %s, price_changed_date = %s WHERE vendor_product_id = %s AND source = %s"""
                    values = ("1", dateTime, vendor_product_id, temp['source'])
                    this.execute(updateQuery, values)
                    conn.commit()
                    logger.info(f"is_price_changed set 1 for vendor_product_id ({vendor_product_id}).")
                updateQuery = """UPDATE TempVendorPricing SET vendorprice_price = %s, vendorprice_finalprice = %s, vendorprice_shipping = %s, product_page_price = %s, In_cart_price = %s, vendorprice_date = %s,vendor_call_for_best_price = %s, vendorprice_stock = %s, vendorprice_stock_text = %s, product_condition = %s, is_rp_calculated = %s, is_member = %s, scraped_by_system = %s
                    WHERE vendor_product_id = %s AND source = %s"""
                values = (temp['vendorprice_price'], temp['vendorprice_finalprice'], temp['vendorprice_shipping'], temp['product_page_price'], temp['In_cart_price'] , dateTime, temp['vendor_call_for_best_price'], temp['vendorprice_stock'], temp['vendorprice_stock_text'] ,temp['product_condition'], '2', '0', temp['scraped_by_system'], vendor_product_id, temp['source'])
                this.execute(updateQuery, values)
                conn.commit()
                logger.info(f"Record Updated for vendor_product_id ({vendor_product_id}) and source ({temp['source']})")
            else:
                insertQuery = """INSERT INTO TempVendorPricing (vendor_product_id, vendorprice_price, vendorprice_finalprice, vendorprice_shipping, product_page_price, In_cart_price, vendorprice_date, vendor_call_for_best_price, vendorprice_stock, vendorprice_stock_text, product_condition, source, is_rp_calculated, is_member, scraped_by_system) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s ,%s,%s, %s)"""
                values = (vendor_product_id, temp['vendorprice_price'], temp['vendorprice_finalprice'], temp['vendorprice_shipping'], temp['product_page_price'], temp['In_cart_price'], dateTime, temp['vendor_call_for_best_price'], temp['vendorprice_stock'], temp['vendorprice_stock_text'], temp['product_condition'], temp['source'], '2', '0', temp['scraped_by_system'])
                this.execute(insertQuery, values)
                conn.commit()
                logger.info(f"Record Inserted for vendor_product_id ({vendor_product_id}) and source ({temp['source']})")
    except mysql.connector.Error as e:
        logger.warning(f"MySQL ERROR vendorTempPricing() >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

def get_table_structure(host, db, user, password, table_name):
    """Retrieve column details from a table, preserving the column order."""
    try:
        conn = mysql.connector.connect(host=host, database=db, user=user, password=password)
        cursor = conn.cursor()            
        cursor.execute(f"DESCRIBE {table_name}")
        structure = [(row[0], row[1], row[2], row[3], row[4], row[5]) for row in cursor.fetchall()]  
        # (Column Name, Column Type, NULL, Key, Default, Extra)
    except Exception as e:
        logger.error(f"Error fetching table structure for {table_name}: {e}")
        structure = []
    finally:
        cursor.close()
        conn.close()
    return structure

def match_table_structure(source_structure, target_structure):
    """Find missing columns with full definitions and their correct positions."""
    target_columns = {col[0]: col for col in target_structure}  # {Column Name: Column Details}
    missing_columns = []

    for index, column in enumerate(source_structure):
        col_name, col_type, is_null, key, default, extra = column
        if col_name not in target_columns:
            after_column = source_structure[index - 1][0] if index > 0 else None
            missing_columns.append((col_name, col_type, is_null, key, default, extra, after_column))
    if missing_columns and len(missing_columns) > 0:
        logger.info(f"Missing columns: {missing_columns}")
    logger.info(f"History Table is up-to-date.")
    return missing_columns

def rpVendorPricingHistory(vendor_product_id, temp, vendor_id):
    dateTime = getDatetime()
    try:
        # save to AF/HP if vendor_id is one of them
        if vendor_id == 10021 or vendor_id == 10024: conn = mysql.connector.connect(host=HOST2, database=DB2, user=USER2, password=PASS2)
        else: conn = mysql.connector.connect(host=HOST3, database=DB3, user=USER3, password=PASS3)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            # check if vendor specific vendorPricing table exists or not
            vendor_pricing_table = f"z_{vendor_id}_VendorPricing"
            this.execute(f"""SELECT * 
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = '{vendor_pricing_table}'
            LIMIT 1""")
            result = this.fetchone()
            source_structure = get_table_structure(HOST, DB, USER, PASS, 'TempVendorPricing')
            if not result:
                logger.info(f"Table {vendor_pricing_table} does not exist. Creating table...")
                column_definitions = []
                primary_key = None  # Store primary key column if exists
                for col_name, col_type, is_null, key, default, extra in source_structure:
                    null_option = "NULL" if is_null == "YES" else "NOT NULL"
                    # Handle default values properly
                    if default is not None:
                        if "timestamp" in col_type.lower() or "datetime" in col_type.lower():
                            default_option = "DEFAULT CURRENT_TIMESTAMP" if default.lower() == "current_timestamp()" else ""
                        else:
                            default_option = f"DEFAULT {repr(default)}"
                    else:
                        default_option = ""
                    extra_option = extra if extra else ""
                    # Ensure AUTO_INCREMENT is properly handled
                    if "auto_increment" in extra.lower():
                        extra_option = "AUTO_INCREMENT"
                        primary_key = col_name  # Store primary key
                    column_definitions.append(f"`{col_name}` {col_type} {null_option} {default_option} {extra_option}")
                create_table_query = f"""
                    CREATE TABLE `{vendor_pricing_table}` (
                        {', '.join(column_definitions)}
                        {f", PRIMARY KEY (`{primary_key}`)" if primary_key else ""}
                    );
                """.strip()
                this.execute(create_table_query)
                conn.commit()
                logger.info(f"Table {vendor_pricing_table} created successfully.")
                logger.info(f"==========================================")
            else:
                if vendor_id == 10021 or vendor_id == 10024:
                    target_structure = get_table_structure(HOST2, DB2, USER2, PASS2, vendor_pricing_table)
                else:
                    target_structure = get_table_structure(HOST3, DB3, USER3, PASS3, vendor_pricing_table)
                missing_columns = match_table_structure(source_structure, target_structure)
                if missing_columns and len(missing_columns) > 0:
                    # Add missing columns if table exists
                    for col_name, col_type, is_null, key, default, extra, after_column in missing_columns:
                        null_option = "NULL" if is_null == "YES" else "NOT NULL"
                        # Handle default values properly
                        if default is not None:
                            if "timestamp" in col_type.lower() or "datetime" in col_type.lower():
                                default_option = "DEFAULT CURRENT_TIMESTAMP" if default.lower() == "current_timestamp()" else ""
                            else:
                                default_option = f"DEFAULT {repr(default)}"
                        else:
                            default_option = ""
                        extra_option = extra if extra else ""
                        after_option = f"AFTER `{after_column}`" if after_column else "FIRST"
                        # Prevent adding AUTO_INCREMENT column incorrectly
                        if "auto_increment" in extra.lower():
                            logger.warning(f"Skipping column `{col_name}` because it has AUTO_INCREMENT.")
                            continue  # Do not add AUTO_INCREMENT column
                        alter_query = f"""
                            ALTER TABLE `{vendor_pricing_table}`
                            ADD COLUMN `{col_name}` {col_type} {null_option} {default_option} {extra_option} {after_option};
                        """.strip()
                        this.execute(alter_query)
                    conn.commit()
                    logger.info(f"Table {vendor_pricing_table} altered successfully.")
                    logger.info(f"==========================================")

            insertQuery = f"""INSERT INTO {vendor_pricing_table} (vendor_product_id, vendorprice_price, vendorprice_finalprice,product_page_price, In_cart_price, vendorprice_date, vendor_call_for_best_price, vendorprice_stock, 
                vendorprice_stock_text, product_condition, source, is_rp_calculated, is_member, scraped_by_system) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            values = (vendor_product_id, temp['vendorprice_price'], temp['vendorprice_finalprice'], temp['product_page_price'], temp['In_cart_price'], dateTime, temp['vendor_call_for_best_price'], temp['vendorprice_stock'],
                       temp['vendorprice_stock_text'], temp['product_condition'], temp['source'], '2', '0', temp['scraped_by_system'])
            this.execute(insertQuery, values)
            conn.commit()
            logger.info(f"Record Inserted for vendor_product_id ({vendor_product_id}) and source ({temp['source']}) In {vendor_pricing_table} history table.")
    except mysql.connector.Error as e:
        logger.warning(f"MySQL ERROR {vendor_pricing_table} >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

# Updating MSRF in Product table
def productMsrpUpdate(product_id, temp):
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            this.execute("SELECT msrp FROM Product WHERE product_id = %s", (product_id,))
            result = this.fetchone()
            if result:
                # Update MSRP
                if temp['msrp']:
                    this.execute("UPDATE Product SET msrp = %s WHERE product_id = %s", (temp['msrp'], product_id))
                    conn.commit()
                    logger.info(f"Record Updated for product_id ({product_id}).")
    except mysql.connector.Error as e:
        logger.warning(f"{product_id} >> MySQL ERROR productMsrpUpdate() >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

# Updating MSRF in ProductVendor table
def productVendorMsrpUpdate(vendor_product_id, temp):
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor(buffered=True)
            this.execute("SELECT msrp FROM ProductVendor WHERE vendor_product_id = %s", (vendor_product_id,))
            result = this.fetchone()
            if result:
                # Update MSRP
                if temp['msrp']:
                    this.execute("UPDATE ProductVendor SET msrp = %s WHERE vendor_product_id = %s", (temp['msrp'], vendor_product_id))
                    conn.commit()
                    logger.info(f"Record Updated for vendor_product_id ({vendor_product_id}).")
    except mysql.connector.Error as e:
        logger.warning(f"{vendor_product_id} >> MySQL ERROR productVendorMsrpUpdate() >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

def getUrls(driver,vendor_id, vendor_url):
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor()
            getVendorURLQuery = """
                SELECT 
                    ProductVendor.vendor_product_id,
                    Product.product_id,
                    Product.product_name,
                    Product.product_mpn,
                    VendorURL.vendor_url,
                    Brand.brand_id,
                    PPS.main_div_css,
                    PPS.price_tag_css,
                    PPS.price_tag2_css,
                    PPS.msrp_tag_css,
                    PPS.mpn_tag_css,
                    PPS.stock_status_tag_css
                FROM VendorURL
                INNER JOIN ProductVendor 
                    ON ProductVendor.vendor_product_id = VendorURL.vendor_product_id
                INNER JOIN Product 
                    ON Product.product_id = ProductVendor.product_id
                INNER JOIN Brand 
                    ON Brand.brand_id = Product.brand_id
                LEFT JOIN ProductPageStructure PPS 
                    ON PPS.vendor_id = ProductVendor.vendor_id 
                    #AND PPS.is_valid = '1'
                WHERE ProductVendor.vendor_id = %s
                    # AND Brand.brand_id = 212 
                    AND Product.product_mpn IS NOT NULL
                    # AND ProductVendor.vendor_sku IN ("K337956","K5831BI","K702320LSH","K3040NCRT6","K5832W","K3983S0","K1040PBW","K1040PCW","K36520","K220362MB","K2703W","9551","K2106Z","K22598Z","K702331SH","K2222IG","K80648SH","723311000","K435695","K21048BL","K2913PGSAA","K2191V4","K9886BBR","KTS161144ABV","K11830NA","K451024BN","K4859B","K4859SG","K4327W","K399896","KTS731154AF","K4246K","K2123Y","K13463CP","85128B1BH","K2129Y","K29088TI","84856P1SH","K98681","84843LBH","K2129L","K29291IB","KT144914RGD","K994914BL","K23688BA03BZL","K29084SG","K2129B","K2129M","K2003K","K14426RGD","K443195","K2924U","K4863B","K2132M","K4454U","K2132TL","K1007562","K43730","K42757","K2885NB","K1814P","K419896","K2934TI","K2128W","F11600NA","K419796","K6554VB","K5961I","K4451ERW","K9033BN","K2405140","K1934CP","K4591TI","K2250U","K2252F","K7213BV","K225225L","KR77764SDCP","K25086SS0","K22166GRGD","K2180IB","K2287155","K98361GBL","K4674B","K4257K","K2213B","K2003DB","K6671","K2250Y","K7960SC","K2147U","K3514FG","K2917J","K98358CP","K9018BN","K221219H","K22173BN","K4597W","K1995BL","K97494CP","KT37393BL","K4247BBI","K240520","K97498CP","K2192W","K2916A","K2916TI","KTLS970744BN","K7108BV","K10590AKBN","K7702AF","K1995CP","K1004724","KT37391BN","K41127HCP","K3142ST","K43406CP","K28987NA","K41127CCP","K6521ST","K2510E","K20905CP")
            """
            this.execute(getVendorURLQuery, [vendor_id,])
            url_list = this.fetchall()

            if url_list:
                logger.info(f"Found {len(url_list)} URLs to process")
                for value in url_list:
                    (
                        vendor_product_id, product_id, product_name, product_mpn,
                        url, brand_id,
                        main_div_css, price_tag_css, price_tag2_css,
                        msrp_tag_css, mpn_tag_css, stock_status_tag_css
                    ) = value

                    if not url:
                        logger.warning(f"Skipping vendor_product_id {vendor_product_id} due to missing URL")
                        continue

                    # if "html&" in url:
                    #     url = url.split("html&")[0] + "html"

                    logger.info(f"Processing URL: {url}")

                    try:
                        structure = {
                            "main_div": main_div_css,
                            "price": price_tag_css,
                            "price2": price_tag2_css,
                            "msrp": msrp_tag_css,
                            "mpn": mpn_tag_css,
                            "stock": stock_status_tag_css
                        }

                        # fetch_product_data(
                        #     driver,
                        #     url,
                        #     product_id,
                        #     vendor_product_id,
                        #     product_mpn,
                        #     brand_id,
                        #     product_name,
                        #     vendor_id,
                        #     structure
                        # )
                        # scraped_by_mpn(driver, product_mpn, vendor_id, structure)
                        return structure
                    except Exception as e:
                        logger.error(f"Error processing URL {url}: {e}")
                        continue
    except mysql.connector.Error as e:
        logger.warning(f"MySQL ERROR getUrls() >> {e}")
    finally:
        if conn.is_connected():
            conn.close()
            this.close()

def getMpns(driver, vendor_id):
    conn = None
    this = None
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor()
            # filterQuery = """
            #     SELECT 
            #         GROUP_CONCAT(DISTINCT p.product_id) AS product_id
            #     FROM Product p
            #     WHERE 
            #         (
            #             EXISTS (
            #                 SELECT 1
            #                 FROM ProductVendor PV2
            #                 INNER JOIN TempVendorPricing TVP1 ON TVP1.vendor_product_id = PV2.vendor_product_id
            #                 WHERE PV2.product_id = p.product_id
            #                 AND PV2.vendor_id = %s
            #                 AND TVP1.source = 'direct_from_website'
            #                 AND TVP1.vendorprice_date BETWEEN DATE_SUB(CURDATE(), INTERVAL 15 DAY) AND CURDATE()
            #             )
            #             OR EXISTS (
            #                 SELECT 1
            #                 FROM VendorWebsiteScrapingMPNStatus VWS
            #                 WHERE VWS.product_id = p.product_id
            #                 AND VWS.vendor_id = %s
            #                 AND VWS.product_status = '0'
            #             )
            #         )"""
            # this.execute(filterQuery,(vendor_id,vendor_id))
            # # product_ids = this.fetchall()
            # product_ids = [str(row[0]) for row in this.fetchall()]

            getVendorURLQuery = f"""
                SELECT DISTINCT
                    p.product_id,
                    b.brand_name,
                    p.product_mpn,
                    vu.vendor_url,
                    pv.vendor_product_id
                FROM Product p
                INNER JOIN Brand b ON b.brand_id = p.brand_id
                INNER JOIN ProductVendor pv ON pv.product_id = p.product_id AND pv.vendor_id = %s
                INNER JOIN ProductVendor pv1 ON pv1.product_id = p.product_id AND pv1.vendor_id = 10021
                INNER JOIN VendorURL vu ON vu.vendor_product_id = pv.vendor_product_id
                INNER JOIN ErpData ON ErpData.vendor_product_id = pv1.vendor_product_id
                INNER JOIN UniversalGroupMapping ON ErpData.mapping_id = UniversalGroupMapping.universal_group_mapping_id
                WHERE pv.vendor_id = %s AND
                pv.is_scraped_for_direct_scraping = '0'
                AND pv.is_processed_for_direct_scraping = '0'
                AND pv.Valid_for_Direct_Website_Scraping = '1'
                AND material_grp LIKE '%AOSPAR%'
                # AND b.brand_id IN (157,756,722,4,763,762,6,730,8,724,740)
                Order by p.product_id Desc
            """
            this.execute(getVendorURLQuery,(vendor_id,vendor_id))
            url_list = this.fetchall()
            if url_list:
                logger.info(f"Found {len(url_list)} URLs to process")
                results = []
                for value in url_list:
                    product_id, brand_name, product_mpn, vendor_url, vendor_product_id = value
                    results.append((product_id, brand_name, product_mpn, vendor_url, vendor_product_id))
                return url_list
            
            logger.debug(f"Re-Setting products")

            MainQuery = """
                SELECT DISTINCT(p.product_id) AS product_id
                FROM Product p
                INNER JOIN Brand b ON b.brand_id = p.brand_id
                INNER JOIN ProductVendor pv ON pv.product_id = p.product_id AND pv.vendor_id = %s
                INNER JOIN ProductVendor pv1 ON pv1.product_id = p.product_id AND pv1.vendor_id = 10021
                INNER JOIN VendorURL vu ON vu.vendor_product_id = pv.vendor_product_id
                WHERE pv.vendor_id = %s
                AND pv.Valid_for_Direct_Website_Scraping = '1'
                Order by p.product_id Desc
            """
            this.execute(MainQuery,(vendor_id,vendor_id))
            result_ids = [str(row[0]) for row in this.fetchall()]
    
            if result_ids:
                placeholders = ",".join(["%s"] * len(result_ids))

                updateQuery = f"""
                    UPDATE ProductVendor
                    SET is_processed_for_direct_scraping = '0',
                        is_scraped_for_direct_scraping = '0'
                    WHERE vendor_id = %s
                    AND product_id IN ({placeholders})
                """

                params = (vendor_id, *result_ids)
                this.execute(updateQuery, params)
                conn.commit()

                return getMpns(driver, vendor_id)
            
    except mysql.connector.Error as e:
        logger.warning(f"MySQL ERROR getUrls() >> {e}")
    finally:
        if this:
            this.close()
        if conn and conn.is_connected():
            conn.close()

if __name__ == '__main__':
    driver = None
    try:
        start = time.perf_counter()

        # # ----------------------------
        # # LOAD VPN CONFIG
        # # ----------------------------
        # with open("vpn.json") as f:
        #     vpn = json.load(f)

        # proxy = random.choice(vpn["VPN_IP_PORT"]).strip()
        # user = vpn["VPN_IP_USER"]
        # password = vpn["VPN_IP_PASS"]

        # logger.info(f"Selected proxy: {proxy}")

        # # ----------------------------
        # # CHROME OPTIONS
        # # ----------------------------
        # options = Options()
        # options.add_argument("--headless=new")
        # options.add_argument("--no-sandbox")
        # options.add_argument("--disable-dev-shm-usage")

        # # ----------------------------
        # # SELENIUM WIRE PROXY CONFIG
        # # ----------------------------
        # seleniumwire_options = {
        #     'proxy': {
        #         'http': f"http://{user}:{password}@{proxy}",
        #         'https': f"http://{user}:{password}@{proxy}",
        #         'no_proxy': 'localhost,127.0.0.1'
        #     }
        # }

        # # ----------------------------
        # # CREATE DRIVER (ONLY ONCE)
        # # ----------------------------
        # driver = webdriver.Chrome(
        #     options=options,
        #     seleniumwire_options=seleniumwire_options
        # )

        # ----------------------------
        # YOUR DATA
        # ----------------------------

        options = ChromeOptions()
        # options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--remote-debugging-port=9222")
        driver = uc.Chrome(version_main=149, options=options)

        vendors = [(10153,"https://www.gsistore.com/")]

        mpns = getMpns(driver, 10153)

        for product_id, brand_name, mpn, product_url, vendor_product_id in mpns:
            for vendor_id, vendor_url in vendors:
                logger.info(f"Starting vendor: {vendor_id} | {vendor_url}")
                try:
                    logger.debug(f"Vendor {vendor_id} >> Processing product_id: {product_id}, mpn: {mpn}, vendor_product_id: {vendor_product_id}")
                    scraped_by_mpn(driver,vendor_id, vendor_url, product_id, brand_name, mpn, product_url, vendor_product_id)
                except Exception as e:
                    logger.error(f"Error in vendor {vendor_id}: {e}")
                    continue

        end = time.perf_counter()
        logger.debug(f"Total execution time: {end - start:.2f} seconds")

    except Exception as e:
        logger.error(f"An error occurred: {e}")

    finally:
        if driver:
            driver.quit()