import os
import time
import mysql.connector
from decimal import Decimal
from operator import itemgetter
from datetime import datetime, timedelta
from modules.runTimeSecrets import HOST, DB, USER, PASS, HOST2, DB2, USER2, PASS2, HOST3, DB3, USER3, PASS3

# ------------------------------- LOGGER -------------------------------
import logging
def loggerInit(logFileName):
    try: os.makedirs("logs")
    except: pass
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s:%(name)s:%(message)s')
    file_handler = logging.FileHandler(f'logs/{logFileName}')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger
logger = loggerInit(logFileName="products.ranking.log")
# ------------------------------- DATES -------------------------------
# today
today_date = datetime.now().strftime("%Y-%m-%d")
# yesterday
yesterday = datetime.now() - timedelta(1)
yesterday_date = yesterday.strftime("%Y-%m-%d")
# 7 days ago date
last_7th_day = datetime.now() - timedelta(7)
last_7th_day_date = last_7th_day.strftime("%Y-%m-%d")
# 30 days ago date
last_30th_day = datetime.now() - timedelta(30)
last_30th_day_date = last_7th_day.strftime("%Y-%m-%d")
# -----------------------------------------------------

# Saving vendor ranking according to final price low to high
def saveRanks(data):
    vendor_product_id, vendor_id, product_id = data
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    logger.debug(f"Finding ranking for product_id ({product_id}) of vendor_id ({vendor_id}).")

    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor()
            # universal vendors to exclude
            this.execute("""
            SELECT
                keyword
            FROM UniversalVendorExclude;""")
            uni_result = this.fetchall()
            universalVendorsToExcludeTemp = []
            if not uni_result:
                universalVendorsToExclude = 0
            else:
                for row in uni_result:
                    this.execute(f"""
                    SELECT
                        GROUP_CONCAT(vendor_id) AS vendor_id
                    FROM Vendor
                    WHERE vendor_website LIKE '%{row[0]}%'
                    """)
                    result = this.fetchone()
                    if len(result) > 0:
                        if result[0] is None:
                            universalVendorsToExclude = 0
                        else:
                            universalVendorsToExcludeTemp.append(result[0])
                    else:
                        universalVendorsToExclude = 0
            if len(universalVendorsToExcludeTemp) > 0: universalVendorsToExclude = ",".join([value for value in universalVendorsToExcludeTemp])
            # vendors to exclude from ranking
            vendorsToExclude = universalVendorsToExclude
            # dates
            last_30th_day_date_date = datetime.strptime(last_30th_day_date, '%Y-%m-%d').date()
            last_7th_day_date_date = datetime.strptime(last_7th_day_date, '%Y-%m-%d').date()
            yesterday_date_date = datetime.strptime(yesterday_date, '%Y-%m-%d').date()
            # ----------------------------------------------------------------------------------------------------------------------------------
            pricing_data = []
            this.execute(f"""
                WITH RankedData AS (
                    SELECT
                        TempVendorPricing.source,
                        Vendor.vendor_name,
                        TempVendorPricing.vendorprice_price,
                        TempVendorPricing.vendorprice_finalprice,
                        TempVendorPricing.vendorprice_shipping,
                        TempVendorPricing.vendorprice_extra_discount,
                        VendorURL.vendor_raw_url as vendor_url,
                        ProductVendor.vendor_product_id,
                        Vendor.vendor_id,
                        TempVendorPricing.is_suspicious,
                        TempVendorPricing.vendor_pricing_id,
                        TempVendorPricing.vendorprice_date,
                        TempVendorPricing.vendorprice_delivery_date,
                        TempVendorPricing.vendorprice_isbackorder,
                        TempVendorPricing.vendorprice_offers,
                        TempVendorPricing.delivery_text,
                        TempVendorPricing.vendorprice_stock_text,
                        TempVendorPricing.vendorprice_stock,
                        DENSE_RANK() OVER (PARTITION BY ProductVendor.vendor_product_id ORDER BY TempVendorPricing.vendorprice_date DESC) AS row_num
                    FROM TempVendorPricing
                    INNER JOIN ProductVendor ON TempVendorPricing.vendor_product_id = ProductVendor.vendor_product_id
                    LEFT JOIN VendorURL ON ProductVendor.vendor_product_id = VendorURL.vendor_product_id
                    INNER JOIN Vendor ON ProductVendor.vendor_id = Vendor.vendor_id
                    WHERE
                        ProductVendor.product_id = {product_id}
                        AND ProductVendor.vendor_id NOT IN ({vendorsToExclude})
                        AND ( TempVendorPricing.vendorprice_date BETWEEN DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND CURDATE() )
                        AND TempVendorPricing.is_suspicious = '0'
                        AND TempVendorPricing.product_condition = 'New'
                        AND TempVendorPricing.vendorprice_price > 0
                        AND TempVendorPricing.marked_as_unmatched = '0'
                        AND ( TempVendorPricing.vendorprice_stock_text <> 'Out of stock online' OR TempVendorPricing.vendorprice_stock_text IS NULL )
                        AND Vendor.vendor_id <> {vendor_id} AND Vendor.vendor_id <> 10024
                    ORDER BY TempVendorPricing.vendorprice_finalprice ASC, ProductVendor.vendor_id = {vendor_id} DESC
                )
                SELECT *
                FROM RankedData
                WHERE row_num = 1;
            """)
            result2 = this.fetchall()
            if result2:
                for row in result2:
                    if vendor_id == 10021 and row[8] == 10024: continue
                    elif vendor_id == 10024 and row[8] == 10021: continue
                    pricing_data.append({
                        "source" : row[0],
                        "vendor_product_id" : row[7],
                        "vendor_name" : row[1],
                        "price" : row[2],
                        "final_price" : row[3],
                        "shipping" : row[4],
                        "discount" : row[5],
                        "vendor_product_url" : row[6],
                        "vendor_id" : row[8],
                        "is_suspicious" : row[9],
                        "vendor_pricing_id" : row[10],
                        "vendorprice_date" : row[11],
                        "delivery_date" : row[12],
                        "is_backorder" : row[13],
                        "delivery_text_gmc" : row[14],
                        "delivery_text_website" : row[15],
                        "stock_text_website" : row[16],
                        "stock" : row[17]
                    })
            # Fetching current product's related products
            this.execute(f"""
                SELECT
                    TempVendorPricing.source,
                    Vendor.vendor_name,
                    TempVendorPricing.vendorprice_price,
                    TempVendorPricing.vendorprice_finalprice,
                    TempVendorPricing.vendorprice_shipping,
                    TempVendorPricing.vendorprice_extra_discount,
                    VendorURL.vendor_raw_url as vendor_url,
                    ProductVendor.vendor_product_id,
                    Vendor.vendor_id,
                    TempVendorPricing.is_suspicious,
                    TempVendorPricing.vendor_pricing_id,
                    TempVendorPricing.vendorprice_date,
                    TempVendorPricing.vendorprice_delivery_date,
                    TempVendorPricing.vendorprice_isbackorder,
                    TempVendorPricing.vendorprice_offers,
                    TempVendorPricing.delivery_text,
                    TempVendorPricing.vendorprice_stock_text,
                    TempVendorPricing.vendorprice_stock
                FROM RelatedProducts_Matching
                INNER JOIN TempVendorPricing ON TempVendorPricing.vendor_product_id = RelatedProducts_Matching.competitor_vendor_product_id
                INNER JOIN ProductVendor ON ProductVendor.vendor_product_id = TempVendorPricing.vendor_product_id
                LEFT JOIN VendorURL ON VendorURL.vendor_product_id = ProductVendor.vendor_product_id
                INNER JOIN Vendor ON Vendor.vendor_id = ProductVendor.vendor_id
                WHERE
                    RelatedProducts_Matching.vendor_product_id = '{vendor_product_id}'
                    AND Vendor.vendor_id <> 10024
                    AND TempVendorPricing.is_suspicious = '0'
                    AND TempVendorPricing.vendorprice_price > 0
                    AND TempVendorPricing.marked_as_unmatched = '0'
                    AND ( TempVendorPricing.vendorprice_stock_text <> 'Out of stock online' OR TempVendorPricing.vendorprice_stock_text IS NULL )
                    AND ( TempVendorPricing.vendorprice_date BETWEEN DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND CURDATE() );
            """)
            result3 = this.fetchall()
            if result3:
                for row in result3:
                    if vendor_id == 10021 and row[8] == 10024: continue
                    elif vendor_id == 10024 and row[8] == 10021: continue
                    pricing_data.append({
                        "source" : row[0],
                        "vendor_product_id" : row[7],
                        "vendor_name" : row[1],
                        "price" : row[2],
                        "final_price" : row[3],
                        "shipping" : row[4],
                        "discount" : row[5],
                        "vendor_product_url" : row[6],
                        "vendor_id" : row[8],
                        "is_suspicious" : row[9],
                        "vendor_pricing_id" : row[10],
                        "vendorprice_date" : row[11],
                        "delivery_date" : row[12],
                        "is_backorder" : row[13],
                        "delivery_text_gmc" : row[14],
                        "delivery_text_website" : row[15],
                        "stock_text_website" : row[16],
                        "stock" : row[17]
                    })
            # --------------------------------------------------------------------------------
            # including our product's sister vendor (AF in case of HP) (HP in case of AF)
            if vendor_id == 10021: sister_vendor_id = 10024
            elif vendor_id == 10024: sister_vendor_id = 10021
            else: sister_vendor_id = None
            sister_vendor_id = None
            if sister_vendor_id != None:
                this.execute(f"""
                    SELECT
                        TempVendorPricing.source,
                        Vendor.vendor_name,
                        TempVendorPricing.vendorprice_price,
                        TempVendorPricing.vendorprice_finalprice,
                        TempVendorPricing.vendorprice_shipping,
                        TempVendorPricing.vendorprice_extra_discount,
                        VendorURL.vendor_raw_url as vendor_url,
                        ProductVendor.vendor_product_id,
                        Vendor.vendor_id,
                        TempVendorPricing.is_suspicious,
                        TempVendorPricing.vendor_pricing_id,
                        TempVendorPricing.vendorprice_date,
                        TempVendorPricing.vendorprice_delivery_date,
                        TempVendorPricing.vendorprice_isbackorder,
                        TempVendorPricing.vendorprice_offers,
                        TempVendorPricing.delivery_text,
                        TempVendorPricing.vendorprice_stock_text,
                        TempVendorPricing.vendorprice_stock
                    FROM TempVendorPricing
                    INNER JOIN ProductVendor ON TempVendorPricing.vendor_product_id = ProductVendor.vendor_product_id
                    LEFT JOIN VendorURL ON ProductVendor.vendor_product_id = VendorURL.vendor_product_id
                    INNER JOIN Vendor ON ProductVendor.vendor_id = Vendor.vendor_id
                    WHERE
                        ProductVendor.product_id = {product_id}
                        AND ProductVendor.vendor_id = {sister_vendor_id}
                        AND TempVendorPricing.is_suspicious = '0'
                        AND TempVendorPricing.product_condition = 'New'
                    ORDER BY
                        CASE 
                            WHEN TempVendorPricing.manual_price_update_date IS NOT NULL 
                                AND TempVendorPricing.manual_price_time_period IS NOT NULL 
                                AND DATEDIFF(CURDATE(), TempVendorPricing.manual_price_update_date) < TempVendorPricing.manual_price_time_period 
                            THEN 1  -- Assign priority for sorting
                            ELSE 2  -- Assign lower priority for sorting
                        END,
                        TempVendorPricing.vendorprice_date DESC,
                        FIELD(TempVendorPricing.source, 'google_main_searched', 'gmc', 'direct_from_website', 'feed')
                    LIMIT 1;
                """)
                result01 = this.fetchone()
                includeSis = False
                if result01:
                    result01 = list(result01)
                    if yesterday_date_date > result01[11]:
                        logger.debug("Sister vendor is outdated.")
                        # Fetching price from ERP data
                        this.execute(f"""
                            SELECT
                                ErpData.website_price,
                                ErpData.update_sales,
                                CouponCode.coupon_percentage
                            FROM ErpData
                            LEFT JOIN CouponCode ON CouponCode.coupon_id = ErpData.promotional_id
                            WHERE
                                vendor_product_id = {result01[7]}
                                AND ErpData.website_price IS NOT NULL
                            LIMIT 1;
                        """)
                        erpSis = this.fetchone()
                        if erpSis:
                            includeSis = True
                            logger.debug("Found in ERP.")
                            # shipping amount
                            if last_30th_day_date_date < result01[11]: shipping_amount = result01[4]
                            else: shipping_amount = 0.00
                            # calculating final amount
                            if erpSis[2] == None:
                                discount_percent = 0.00
                                final_amount = float(erpSis[0]) + float(shipping_amount)
                            else:
                                discount_percent = erpSis[2]
                                discount_amount = ( float(discount_percent) / 100 ) * float(erpSis[0])
                                final_amount = ( float(erpSis[0]) - float(discount_amount) ) + float(shipping_amount)

                            result01[2] = erpSis[0]
                            result01[3] = final_amount
                            result01[4] = shipping_amount
                            result01[5] = discount_percent
                            result01[11] = erpSis[1]
                            result01[0] = 'direct_from_website'

                            logger.debug(f"Price ({erpSis[0]}), final price ({final_amount}), shipping ({shipping_amount}) & discount ({erpSis[2]}) are changed from ERP.")
                        else:
                            logger.debug("Not found in ERP.")
                    else:
                        # checking if the price is more than zero
                        if result01[2] > 0:
                            includeSis = True
                            logger.debug("Sister vendor is up to date.")
                        else:
                            logger.debug("Sister vendor is up to date but price is 0.")
                            # Fetching price from ERP data
                            this.execute(f"""
                                SELECT
                                    ErpData.website_price,
                                    ErpData.update_sales,
                                    CouponCode.coupon_percentage
                                FROM ErpData
                                LEFT JOIN CouponCode ON CouponCode.coupon_id = ErpData.promotional_id
                                WHERE
                                    vendor_product_id = {result01[7]}
                                    AND ErpData.website_price IS NOT NULL
                                LIMIT 1;
                            """)
                            erpSis = this.fetchone()
                            if erpSis:
                                includeSis = True
                                logger.debug("Found in ERP.")
                                # shipping amount
                                if last_30th_day_date_date < result01[11]: shipping_amount = result01[4]
                                else: shipping_amount = 0.00
                                # calculating final amount
                                if erpSis[2] == None:
                                    discount_percent = 0.00
                                    final_amount = float(erpSis[0]) + float(shipping_amount)
                                else:
                                    discount_percent = erpSis[2]
                                    discount_amount = ( float(discount_percent) / 100 ) * float(erpSis[0])
                                    final_amount = ( float(erpSis[0]) - float(discount_amount) ) + float(shipping_amount)
                                
                                result01[2] = erpSis[0]
                                result01[3] = final_amount
                                result01[4] = shipping_amount
                                result01[5] = discount_percent
                                result01[11] = erpSis[1]
                                result01[0] = 'direct_from_website'

                                logger.debug(f"Price ({erpSis[0]}), final price ({final_amount}), shipping ({shipping_amount}) & discount ({erpSis[2]}) are changed from ERP.")
                            else:
                                logger.debug("Not found in ERP.")
                    # including sister vendor
                    if includeSis:
                        pricing_data.append({
                            "source" : result01[0],
                            "vendor_product_id" : result01[7],
                            "vendor_name" : result01[1],
                            "price" : result01[2],
                            "final_price" : result01[3],
                            "shipping" : result01[4],
                            "discount" : result01[5],
                            "vendor_product_url" : result01[6],
                            "vendor_id" : result01[8],
                            "is_suspicious" : result01[9],
                            "vendor_pricing_id" : result01[10],
                            "vendorprice_date" : result01[11],
                            "delivery_date" : result01[12],
                            "is_backorder" : result01[13],
                            "delivery_text_gmc" : result01[14],
                            "delivery_text_website" : result01[15],
                            "stock_text_website" : result01[16],
                            "stock" : result01[17]
                        })
                else:
                    logger.debug("Sister vendor not found.")
            # --------------------------------------------------------------------------------
            if len(pricing_data) > 0: foundOthers = True
            else: foundOthers = False
            # including our product in list even if its data is outdated
            this.execute(f"""
                SELECT
                    TempVendorPricing.source,
                    Vendor.vendor_name,
                    TempVendorPricing.vendorprice_price,
                    TempVendorPricing.vendorprice_finalprice,
                    TempVendorPricing.vendorprice_shipping,
                    TempVendorPricing.vendorprice_extra_discount,
                    VendorURL.vendor_raw_url as vendor_url,
                    ProductVendor.vendor_product_id,
                    Vendor.vendor_id,
                    TempVendorPricing.is_suspicious,
                    TempVendorPricing.vendor_pricing_id,
                    TempVendorPricing.vendorprice_date,
                    TempVendorPricing.vendorprice_delivery_date,
                    TempVendorPricing.vendorprice_isbackorder,
                    TempVendorPricing.vendorprice_offers,
                    TempVendorPricing.delivery_text,
                    TempVendorPricing.vendorprice_stock_text,
                    TempVendorPricing.vendorprice_stock
                FROM TempVendorPricing
                INNER JOIN ProductVendor ON TempVendorPricing.vendor_product_id = ProductVendor.vendor_product_id
                LEFT JOIN VendorURL ON ProductVendor.vendor_product_id = VendorURL.vendor_product_id
                INNER JOIN Vendor ON ProductVendor.vendor_id = Vendor.vendor_id
                WHERE
                    ProductVendor.product_id = {product_id}
                    AND ProductVendor.vendor_id = {vendor_id}
                    AND TempVendorPricing.is_suspicious = '0'
                    AND TempVendorPricing.marked_as_unmatched = '0'
                    AND TempVendorPricing.product_condition = 'New'
                ORDER BY
                    CASE 
                        WHEN TempVendorPricing.manual_price_update_date IS NOT NULL 
                            AND TempVendorPricing.manual_price_time_period IS NOT NULL 
                            AND DATEDIFF(CURDATE(), TempVendorPricing.manual_price_update_date) < TempVendorPricing.manual_price_time_period 
                        THEN 1  -- Assign priority for sorting
                        ELSE 2  -- Assign lower priority for sorting
                    END,
                    TempVendorPricing.vendorprice_date DESC,
                    FIELD(TempVendorPricing.source, 'google_main_searched', 'gmc', 'direct_from_website', 'feed')
                LIMIT 1;
            """)
            result0 = this.fetchone()
            include = False
            if result0:
                result0 = list(result0)
                last_7th_day_date_date = datetime.strptime(last_7th_day_date, '%Y-%m-%d').date()
                if last_7th_day_date_date > result0[11]:
                    logger.debug("Our vendor is outdated.")
                    # Fetching price from ERP data
                    this.execute(f"""
                        SELECT
                            ErpData.website_price,
                            ErpData.update_sales,
                            CouponCode.coupon_percentage
                        FROM ErpData
                        LEFT JOIN CouponCode ON CouponCode.coupon_id = ErpData.promotional_id
                        WHERE
                            vendor_product_id = {vendor_product_id}
                            AND ErpData.website_price IS NOT NULL
                        LIMIT 1;
                    """)
                    erp = this.fetchone()
                    if erp:
                        include = True
                        logger.debug("Found in ERP.")
                        # shipping amount
                        shipping_amount = result0[4] if result0[4] is not None else 0.00
                        if last_30th_day_date_date < result0[11]: 
                            pass
                        else: shipping_amount = 0.00
                        # calculating final amount
                        if erp[2] == None:
                            discount_percent = 0.00
                            final_amount = float(erp[0]) + float(shipping_amount)
                        else:
                            discount_percent = erp[2]
                            discount_amount = ( float(discount_percent) / 100 ) * float(erp[0])
                            final_amount = ( float(erp[0]) - float(discount_amount) ) + float(shipping_amount)
                        
                        result0[2] = erp[0]
                        result0[3] = final_amount
                        result0[4] = shipping_amount
                        result0[5] = discount_percent
                        result0[11] = erp[1]
                        result0[0] = 'direct_from_website'

                        logger.debug("Price, final price, shipping & discount are changed from ERP.")
                    else:
                        logger.debug("Not found in ERP.")
                else:
                    # checking if the price is more than zero
                    if result0[2] > 0:
                        this.execute(f"""
                            SELECT
                                ErpData.website_price,
                                ErpData.update_sales,
                                CouponCode.coupon_percentage
                            FROM ErpData
                            LEFT JOIN CouponCode ON CouponCode.coupon_id = ErpData.promotional_id
                            WHERE
                                vendor_product_id = {vendor_product_id}
                                AND ErpData.website_price IS NOT NULL
                            LIMIT 1;
                        """)
                        erp = this.fetchone()
                        if erp:
                            include = True
                            logger.debug("Found in ERP.")
                            # shipping amount
                            shipping_amount = result0[4] if result0[4] is not None else 0.00
                            if last_30th_day_date_date < result0[11]: 
                                pass
                            else: shipping_amount = 0.00
                            # calculating final amount
                            if erp[2] == None:
                                discount_percent = 0.00
                                final_amount = float(result0[2]) + float(shipping_amount)
                            else:
                                discount_percent = erp[2]
                                discount_amount = ( float(discount_percent) / 100 ) * float(result0[2])
                                final_amount = ( float(result0[2]) - float(discount_amount) ) + float(shipping_amount)
                            
                            result0[2] = result0[2]
                            result0[3] = final_amount
                            result0[4] = shipping_amount
                            result0[5] = discount_percent
                            result0[11] = result0[11]
                            result0[0] = result0[0]
                            
                            logger.debug("Price, final price, shipping & discount are changed from ERP.")
                        else:
                            include = True
                            logger.debug("Not found in ERP.")
                    else:
                        logger.debug("Our vendor is up to date but price is 0.")
                        # Fetching price from ERP data
                        this.execute(f"""
                            SELECT
                                ErpData.website_price,
                                ErpData.update_sales,
                                CouponCode.coupon_percentage
                            FROM ErpData
                            LEFT JOIN CouponCode ON CouponCode.coupon_id = ErpData.promotional_id
                            WHERE
                                vendor_product_id = {vendor_product_id}
                                AND ErpData.website_price IS NOT NULL
                            LIMIT 1;
                        """)
                        erp = this.fetchone()
                        if erp:
                            include = True
                            logger.debug("Found in ERP.")
                            # shipping amount
                            shipping_amount = result0[4] if result0[4] is not None else 0.00
                            if last_30th_day_date_date < result0[11]: 
                                pass
                            else: shipping_amount = 0.00
                            # calculating final amount
                            if erp[2] == None:
                                discount_percent = 0.00
                                final_amount = float(erp[0]) + float(shipping_amount)
                            else:
                                discount_percent = erp[2]
                                discount_amount = ( float(discount_percent) / 100 ) * float(erp[0])
                                final_amount = ( float(erp[0]) - float(discount_amount) ) + float(shipping_amount)
                            
                            result0[2] = erp[0]
                            result0[3] = final_amount
                            result0[4] = shipping_amount
                            result0[5] = discount_percent
                            result0[11] = erp[1]
                            result0[0] = 'direct_from_website'
                            
                            logger.debug("Price, final price, shipping & discount are changed from ERP.")
                        else:
                            logger.debug("Not found in ERP.")
                # including our vendor
                if include:
                    pricing_data.append({
                        "source" : result0[0],
                        "vendor_product_id" : result0[7],
                        "vendor_name" : result0[1],
                        "price" : result0[2],
                        "final_price" : result0[3],
                        "shipping" : result0[4],
                        "discount" : result0[5],
                        "vendor_product_url" : result0[6],
                        "vendor_id" : result0[8],
                        "is_suspicious" : result0[9],
                        "vendor_pricing_id" : result0[10],
                        "vendorprice_date" : result0[11],
                        "delivery_date" : result0[12],
                        "is_backorder" : result0[13],
                        "delivery_text_gmc" : result0[14],
                        "delivery_text_website" : result0[15],
                        "stock_text_website" : result0[16],
                        "stock" : result0[17]
                    })
                else:
                    current_vendor_pricing_id = result0[10]
            else:
                logger.debug("Our vendor not found.")
                current_vendor_pricing_id = None
            # ----------------------------------------------------------------------------------------
            if len(pricing_data) > 0 and foundOthers:
                # removing exact duplicates
                pricing_data = [dict(tupl) for tupl in {tuple(dict.items()) for dict in pricing_data}]
                # convert final_price to Decimal
                for data in pricing_data:
                    data['final_price'] = Decimal(str(data['final_price']))
                
                # sorting in ascending order of final price
                pricing_data = sorted(pricing_data, key=itemgetter('final_price'))
                sources, sameFinalPrices, priceToCompare, index = {}, {}, 0.00, 0
                productPrices, removeOurVendorFromRanking, indexesToRemove = {}, False, []

                try:
                    for seller in pricing_data:
                        # finding price existence times of each vendor
                        if seller['is_suspicious'] == '0':
                            if seller['price'] in productPrices:
                                productPrices[seller['price']] = productPrices[seller['price']] + 1
                            else:
                                productPrices[seller['price']] = 1
                        # moving up our current vendor if the price is same with other vendors
                        if index == 0:
                            sameFinalPrices = { index: seller['vendor_id'] }
                        if priceToCompare == seller['final_price']:
                            sameFinalPrices[index] = seller['vendor_id']
                            if vendor_id == seller['vendor_id']:
                                first_key = next(iter(sameFinalPrices))
                                ourVendor = pricing_data[index]
                                pricing_data[index] = pricing_data[first_key]
                                pricing_data[first_key] = ourVendor
                        else:
                            sameFinalPrices = {
                                index: seller['vendor_id']
                            }
                        priceToCompare = seller['final_price']
                        # Ranking source priority order
                        # direct_from_website_as_member > google_main_searched > gmc > direct_from_website > google_shopping_searched > feed
                        if seller['vendor_product_id'] in sources:
                            # SOURCE `direct_from_website_as_member`
                            if 'direct_from_website_as_member' in sources[seller['vendor_product_id']]['sources']:
                                indexesToRemove.append(index)
                            elif seller['source'] == 'direct_from_website_as_member':
                                indexesToRemove.append(sources[seller['vendor_product_id']]['index'])
                                sources[seller['vendor_product_id']] = {
                                    'sources': [seller['source']],
                                    'index': index
                                }
                                if vendor_id == seller['vendor_id']:
                                    current_vendor_index = index
                                    current_vendor_final_price = seller['final_price']
                                    current_vendor_pricing_id = seller['vendor_pricing_id']
                                    last_7th_day_date_date = datetime.strptime(last_7th_day_date, "%Y-%m-%d").date()
                                    if seller['vendorprice_date'] < last_7th_day_date_date:
                                        removeOurVendorFromRanking = True
                                    elif current_vendor_final_price == None:
                                        removeOurVendorFromRanking = True
                            # SOURCE `google_main_searched`
                            elif 'google_main_searched' in sources[seller['vendor_product_id']]['sources']:
                                indexesToRemove.append(index)
                            elif seller['source'] == 'google_main_searched':
                                indexesToRemove.append(sources[seller['vendor_product_id']]['index'])
                                sources[seller['vendor_product_id']] = {
                                    'sources': [seller['source']],
                                    'index': index
                                }
                                if vendor_id == seller['vendor_id']:
                                    current_vendor_index = index
                                    current_vendor_final_price = seller['final_price']
                                    current_vendor_pricing_id = seller['vendor_pricing_id']
                                    last_7th_day_date_date = datetime.strptime(last_7th_day_date, "%Y-%m-%d").date()
                                    if seller['vendorprice_date'] < last_7th_day_date_date:
                                        removeOurVendorFromRanking = True
                                    elif current_vendor_final_price == None:
                                        removeOurVendorFromRanking = True
                            # SOURCE `gmc`
                            elif 'gmc' in sources[seller['vendor_product_id']]['sources']:
                                indexesToRemove.append(index)
                            elif seller['source'] == 'gmc':
                                indexesToRemove.append(sources[seller['vendor_product_id']]['index'])
                                sources[seller['vendor_product_id']] = {
                                    'sources': [seller['source']],
                                    'index': index
                                }
                                if vendor_id == seller['vendor_id']:
                                    current_vendor_index = index
                                    current_vendor_final_price = seller['final_price']
                                    current_vendor_pricing_id = seller['vendor_pricing_id']
                                    last_7th_day_date_date = datetime.strptime(last_7th_day_date, "%Y-%m-%d").date()
                                    if seller['vendorprice_date'] < last_7th_day_date_date:
                                        removeOurVendorFromRanking = True
                                    elif current_vendor_final_price == None:
                                        removeOurVendorFromRanking = True
                            # SOURCE `direct_from_website`
                            elif 'direct_from_website' in sources[seller['vendor_product_id']]['sources']:
                                indexesToRemove.append(index)
                            elif seller['source'] == 'direct_from_website':
                                indexesToRemove.append(sources[seller['vendor_product_id']]['index'])
                                sources[seller['vendor_product_id']] = {
                                    'sources': [seller['source']],
                                    'index': index
                                }
                                if vendor_id == seller['vendor_id']:
                                    current_vendor_index = index
                                    current_vendor_final_price = seller['final_price']
                                    current_vendor_pricing_id = seller['vendor_pricing_id']
                                    last_7th_day_date_date = datetime.strptime(last_7th_day_date, "%Y-%m-%d").date()
                                    if seller['vendorprice_date'] < last_7th_day_date_date:
                                        removeOurVendorFromRanking = True
                                    elif current_vendor_final_price == None:
                                        removeOurVendorFromRanking = True
                            # SOURCE `google_shopping_searched`
                            elif 'google_shopping_searched' in sources[seller['vendor_product_id']]['sources']:
                                indexesToRemove.append(index)
                            elif seller['source'] == 'google_shopping_searched':
                                indexesToRemove.append(sources[seller['vendor_product_id']]['index'])
                                sources[seller['vendor_product_id']] = {
                                    'sources': [seller['source']],
                                    'index': index
                                }
                                if vendor_id == seller['vendor_id']:
                                    current_vendor_index = index
                                    current_vendor_final_price = seller['final_price']
                                    current_vendor_pricing_id = seller['vendor_pricing_id']
                                    last_7th_day_date_date = datetime.strptime(last_7th_day_date, "%Y-%m-%d").date()
                                    if seller['vendorprice_date'] < last_7th_day_date_date:
                                        removeOurVendorFromRanking = True
                                    elif current_vendor_final_price == None:
                                        removeOurVendorFromRanking = True
                            # SOURCE `feed`
                            elif seller['source'] == 'feed':
                                indexesToRemove.append(index)
                        else:
                            sources[seller['vendor_product_id']] = {
                                'sources': [seller['source']],
                                'index': index
                            }
                            if vendor_id == seller['vendor_id']:
                                current_vendor_index = index
                                current_vendor_final_price = seller['final_price']
                                current_vendor_pricing_id = seller['vendor_pricing_id']
                                last_7th_day_date_date = datetime.strptime(last_7th_day_date, "%Y-%m-%d").date()
                                if seller['vendorprice_date'] < last_7th_day_date_date:
                                    removeOurVendorFromRanking = True
                                elif current_vendor_final_price == None:
                                    removeOurVendorFromRanking = True
                        index += 1
                except Exception as e:
                    logger.debug(f'Ranking loop ({vendor_product_id}) >> {e}')
                # if current vednor not found then skip the process
                if current_vendor_pricing_id == None:
                    return
                # Removing unwanted vendors from ranking list
                for indexToRemove in indexesToRemove:
                    try: del pricing_data[indexToRemove]
                    except: pass
                # Removing our vendor from ranking if our pricing data is outdated
                if removeOurVendorFromRanking:
                    del pricing_data[current_vendor_index]
                # finding price existence times of each vendor
                pricesExistenceTimes = sorted(productPrices.items(), key=lambda x:x[1], reverse=True)
                pricesExistenceTimes = dict(pricesExistenceTimes)
                mostExistingPricePercent = ( next(iter(pricesExistenceTimes.values())) / len(pricesExistenceTimes) ) * 100
                # assumed_map_price
                if mostExistingPricePercent > 60 and len(pricing_data) > 4:
                    assumed_map_price = next(iter(pricesExistenceTimes))
                # Top five vendors
                rankedVendors, lowestFiveVendors, rank = {}, pricing_data[:5], 1                                
                for data in lowestFiveVendors:
                    if rank == 1:
                        try:
                            # Rank 1
                            rankedVendors['first_vendor_product_id'] = data['vendor_product_id']
                            rankedVendors['first_vendor_name'] = data['vendor_name']
                            rankedVendors['first_vendor_price'] = data['price']
                            rankedVendors['first_vendor_final_price'] = data['final_price']
                            rankedVendors['first_vendor_shipping'] = data['shipping']
                            rankedVendors['first_vendor_extra_discount'] = data['discount']
                            rankedVendors['first_vendor_product_url'] = data['vendor_product_url']
                            rankedVendors['first_vendor_source'] = data['source']
                            rankedVendors['first_vendor_delivery_date'] = data['delivery_date']
                            rankedVendors['first_vendor_is_backorder'] = data['is_backorder']
                            rankedVendors['first_vendor_delivery_text_gmc'] = data['delivery_text_gmc']
                            rankedVendors['first_vendor_delivery_text_website'] = data['delivery_text_website']
                            rankedVendors['first_vendor_stock_text_website'] = data['stock_text_website']
                            rankedVendors['first_vendor_price_date'] = data['vendorprice_date']
                            rankedVendors['first_vendor_stock'] = data['stock']
                            try:
                                current_vendor_final_price
                            except:
                                if not include:
                                    current_vendor_final_price = None
                            # Percentage
                            if current_vendor_final_price == None:
                                percentage = 0.00
                            else:
                                if data['final_price'] > 0:
                                    percent = ((float(current_vendor_final_price) - float(data['final_price'])) / float(data['final_price'])) * 100
                                    percentage = float(str(round(percent, 2)))
                                else:
                                    percentage = 0.00
                        except Exception as e:
                            logger.debug(f"Rank 1 ERROR({vendor_product_id}) >> {e}")
                    elif rank == 2:
                        try:
                            # Rank 2
                            rankedVendors['second_vendor_product_id'] = data['vendor_product_id']
                            rankedVendors['second_vendor_name'] = data['vendor_name']
                            rankedVendors['second_vendor_price'] = data['price']
                            rankedVendors['second_vendor_final_price'] = data['final_price']
                            rankedVendors['second_vendor_shipping'] = data['shipping']
                            rankedVendors['second_vendor_extra_discount'] = data['discount']
                            rankedVendors['second_vendor_product_url'] = data['vendor_product_url']
                            rankedVendors['second_vendor_source'] = data['source']
                            rankedVendors['second_vendor_delivery_date'] = data['delivery_date']
                            rankedVendors['second_vendor_is_backorder'] = data['is_backorder']
                            rankedVendors['second_vendor_delivery_text_gmc'] = data['delivery_text_gmc']
                            rankedVendors['second_vendor_delivery_text_website'] = data['delivery_text_website']
                            rankedVendors['second_vendor_stock_text_website'] = data['stock_text_website']
                            rankedVendors['second_vendor_price_date'] = data['vendorprice_date']
                            rankedVendors['second_vendor_stock'] = data['stock']
                            try:
                                current_vendor_final_price
                            except:
                                if not include:
                                    current_vendor_final_price = None
                            # Second Percentage
                            if current_vendor_final_price == None:
                                second_percentage = 0.00
                            else:
                                if data['final_price'] > 0:
                                    second_percent = ((float(current_vendor_final_price) - float(data['final_price'])) / float(data['final_price'])) * 100
                                    second_percent = float(str(round(second_percent, 2)))
                                else:
                                    second_percent = 0.00
                                # resetting the percentage if it was 0
                                if percentage == 0.00 or percentage == 0:
                                    percentage = second_percent
                                second_percentage = second_percent
                        except Exception as e:
                            logger.debug(f"Rank 2 ERROR({vendor_product_id}) >> {e}")
                    elif rank == 3:
                        try:
                            # Rank 3
                            rankedVendors['third_vendor_product_id'] = data['vendor_product_id']
                            rankedVendors['third_vendor_name'] = data['vendor_name']
                            rankedVendors['third_vendor_price'] = data['price']
                            rankedVendors['third_vendor_final_price'] = data['final_price']
                            rankedVendors['third_vendor_shipping'] = data['shipping']
                            rankedVendors['third_vendor_extra_discount'] = data['discount']
                            rankedVendors['third_vendor_product_url'] = data['vendor_product_url']
                            rankedVendors['third_vendor_source'] = data['source']
                            rankedVendors['third_vendor_delivery_date'] = data['delivery_date']
                            rankedVendors['third_vendor_is_backorder'] = data['is_backorder']
                            rankedVendors['third_vendor_delivery_text_gmc'] = data['delivery_text_gmc']
                            rankedVendors['third_vendor_delivery_text_website'] = data['delivery_text_website']
                            rankedVendors['third_vendor_stock_text_website'] = data['stock_text_website']
                            rankedVendors['third_vendor_price_date'] = data['vendorprice_date']
                            rankedVendors['third_vendor_stock'] = data['stock']
                        except Exception as e:
                            logger.debug(f"Rank 3 ERROR({vendor_product_id}) >> {e}")
                    elif rank == 4:
                        try:
                            # Rank 4
                            rankedVendors['fourth_vendor_product_id'] = data['vendor_product_id']
                            rankedVendors['fourth_vendor_name'] = data['vendor_name']
                            rankedVendors['fourth_vendor_price'] = data['price']
                            rankedVendors['fourth_vendor_final_price'] = data['final_price']
                            rankedVendors['fourth_vendor_shipping'] = data['shipping']
                            rankedVendors['fourth_vendor_extra_discount'] = data['discount']
                            rankedVendors['fourth_vendor_product_url'] = data['vendor_product_url']
                            rankedVendors['fourth_vendor_source'] = data['source']
                            rankedVendors['fourth_vendor_delivery_date'] = data['delivery_date']
                            rankedVendors['fourth_vendor_is_backorder'] = data['is_backorder']
                            rankedVendors['fourth_vendor_delivery_text_gmc'] = data['delivery_text_gmc']
                            rankedVendors['fourth_vendor_delivery_text_website'] = data['delivery_text_website']
                            rankedVendors['fourth_vendor_stock_text_website'] = data['stock_text_website']
                            rankedVendors['fourth_vendor_price_date'] = data['vendorprice_date']
                            rankedVendors['fourth_vendor_stock'] = data['stock']
                        except Exception as e:
                            logger.debug(f"Rank 4 ERROR({vendor_product_id}) >> {e}")
                    elif rank == 5:
                        try:
                            # Rank 5
                            rankedVendors['fifth_vendor_product_id'] = data['vendor_product_id']
                            rankedVendors['fifth_vendor_name'] = data['vendor_name']
                            rankedVendors['fifth_vendor_price'] = data['price']
                            rankedVendors['fifth_vendor_final_price'] = data['final_price']
                            rankedVendors['fifth_vendor_shipping'] = data['shipping']
                            rankedVendors['fifth_vendor_extra_discount'] = data['discount']
                            rankedVendors['fifth_vendor_product_url'] = data['vendor_product_url']
                            rankedVendors['fifth_vendor_source'] = data['source']
                            rankedVendors['fifth_vendor_delivery_date'] = data['delivery_date']
                            rankedVendors['fifth_vendor_is_backorder'] = data['is_backorder']
                            rankedVendors['fifth_vendor_delivery_text_gmc'] = data['delivery_text_gmc']
                            rankedVendors['fifth_vendor_delivery_text_website'] = data['delivery_text_website']
                            rankedVendors['fifth_vendor_stock_text_website'] = data['stock_text_website']
                            rankedVendors['fifth_vendor_price_date'] = data['vendorprice_date']
                            rankedVendors['fifth_vendor_stock'] = data['stock']
                        except Exception as e:
                            logger.debug(f"Rank 5 ERROR({vendor_product_id}) >> {e}")
                    rank += 1
                # percentage
                try: rankedVendors['percentage'] = percentage
                except: pass
                # second_percentage
                try: rankedVendors['second_percentage'] = second_percentage
                except: pass
                # Assumed MAP Price
                try: rankedVendors['assumed_map_price'] = assumed_map_price
                except: pass
                # Making mysql queries to update product's vendor ranking
                column, total_columns = 1, len(rankedVendors)
                update_values = []
                update_query = "UPDATE TempVendorPricing SET"
                for key, val in rankedVendors.items():
                    update_values.append(val)
                    if column == total_columns:
                        update_query += f" {key} = %s"
                    else:
                        update_query += f" {key} = %s,"
                    column += 1
                update_query += f" WHERE vendor_pricing_id = {current_vendor_pricing_id};"
                # making rank columns empty
                this.execute("""
                    UPDATE TempVendorPricing
                    SET
                        first_vendor_product_id = NULL, first_vendor_name = NULL, first_vendor_price = NULL, first_vendor_final_price = NULL, first_vendor_shipping = NULL,
                        first_vendor_extra_discount = NULL, first_vendor_product_url = NULL, first_vendor_source = NULL, first_vendor_delivery_date = NULL,
                        first_vendor_is_backorder = 'no', first_vendor_delivery_text_gmc = NULL, first_vendor_delivery_text_website = NULL, first_vendor_stock_text_website = NULL,
                        first_vendor_price_date = NULL, first_vendor_stock = NULL, second_vendor_product_id = NULL, second_vendor_name = NULL, second_vendor_price = NULL,
                        second_vendor_final_price = NULL, second_vendor_shipping = NULL, second_vendor_extra_discount = NULL, second_vendor_product_url = NULL,
                        second_vendor_source = NULL, second_vendor_delivery_date = NULL, second_vendor_is_backorder = 'no', second_vendor_delivery_text_gmc = NULL,
                        second_vendor_delivery_text_website = NULL, second_vendor_stock_text_website = NULL, second_vendor_price_date = NULL, second_vendor_stock = NULL,
                        third_vendor_product_id = NULL, third_vendor_name = NULL, third_vendor_price = NULL, third_vendor_final_price = NULL, third_vendor_shipping = NULL,
                        third_vendor_extra_discount = NULL, third_vendor_product_url = NULL, third_vendor_source = NULL, third_vendor_delivery_date = NULL,
                        third_vendor_is_backorder = 'no', third_vendor_delivery_text_gmc = NULL, third_vendor_delivery_text_website = NULL, third_vendor_stock_text_website = NULL,
                        third_vendor_price_date = NULL, third_vendor_stock = NULL, fourth_vendor_product_id = NULL, fourth_vendor_name = NULL, fourth_vendor_price = NULL,
                        fourth_vendor_final_price = NULL, fourth_vendor_shipping = NULL, fourth_vendor_extra_discount = NULL, fourth_vendor_product_url = NULL,
                        fourth_vendor_source = NULL, fourth_vendor_delivery_date = NULL, fourth_vendor_is_backorder = 'no', fourth_vendor_delivery_text_gmc = NULL,
                        fourth_vendor_delivery_text_website = NULL, fourth_vendor_stock_text_website = NULL, fourth_vendor_price_date = NULL, fourth_vendor_stock = NULL,
                        fifth_vendor_product_id = NULL, fifth_vendor_name = NULL, fifth_vendor_price = NULL, fifth_vendor_final_price = NULL, fifth_vendor_shipping = NULL,
                        fifth_vendor_extra_discount = NULL, fifth_vendor_product_url = NULL, fifth_vendor_source = NULL, fifth_vendor_delivery_date = NULL,
                        fifth_vendor_is_backorder = 'no', fifth_vendor_delivery_text_gmc = NULL, fifth_vendor_delivery_text_website = NULL, fifth_vendor_stock_text_website = NULL,
                        fifth_vendor_price_date = NULL, fifth_vendor_stock = NULL, percentage = NULL, second_percentage = NULL, assumed_map_price = NULL, is_rp_calculated = '0'
                    WHERE vendor_pricing_id = %s;""", (
                        current_vendor_pricing_id,
                    )
                )
                conn.commit()
                if this.rowcount == 1:
                    logger.debug(f"Ranks are set null vendor_pricing_id ({current_vendor_pricing_id})")
                # updating ranking
                this.execute(update_query, update_values)
                conn.commit()
                if this.rowcount == 1:
                    logger.debug(f"Pricing data updated for vendor_pricing_id ({current_vendor_pricing_id}) ({vendor_id} X {product_id})")
                # get last updated record details
                this.execute("SELECT vendor_product_id, vendorprice_date, source, product_condition FROM TempVendorPricing WHERE vendor_pricing_id = %s LIMIT 1;", (current_vendor_pricing_id,))
                last_updated = this.fetchone()
                # data to insert into history table
                this.execute("""
                    SELECT
                        vendor_product_id,
                        vendorprice_price, vendorprice_finalprice, vendorprice_date, vendorprice_shipping, vendorprice_return, vendorprice_stock, vendorprice_stock_text, vendorprice_stockdate,
                        vendorprice_isbackorder, is_active, vendorprice_offers, vendorprice_delivery_date, delivery_text, vendorprice_extra_discount, currency, rank, source, shipping_time,
                        product_condition, sales, average_price, is_found, is_suspicious, marketing_message, competitor_count, same_price_vendor_count,
                        first_vendor_product_id, first_vendor_name, first_vendor_price, first_vendor_final_price, first_vendor_shipping, first_vendor_extra_discount, first_vendor_product_url, first_vendor_source,
                        first_vendor_delivery_date, first_vendor_is_backorder, first_vendor_delivery_text_gmc, first_vendor_delivery_text_website, first_vendor_stock_text_website, first_vendor_price_date, first_vendor_stock,
                        second_vendor_product_id, second_vendor_name, second_vendor_price, second_vendor_final_price, second_vendor_shipping, second_vendor_extra_discount, second_vendor_product_url, second_vendor_source,
                        second_vendor_delivery_date, second_vendor_is_backorder, second_vendor_delivery_text_gmc, second_vendor_delivery_text_website, second_vendor_stock_text_website, second_vendor_price_date, second_vendor_stock,
                        third_vendor_product_id, third_vendor_name, third_vendor_price, third_vendor_final_price, third_vendor_shipping, third_vendor_extra_discount, third_vendor_product_url, third_vendor_source,
                        third_vendor_delivery_date, third_vendor_is_backorder, third_vendor_delivery_text_gmc, third_vendor_delivery_text_website, third_vendor_stock_text_website, third_vendor_price_date, third_vendor_stock,
                        fourth_vendor_product_id, fourth_vendor_name, fourth_vendor_price, fourth_vendor_final_price, fourth_vendor_shipping, fourth_vendor_extra_discount, fourth_vendor_product_url, fourth_vendor_source,
                        fourth_vendor_delivery_date, fourth_vendor_is_backorder, fourth_vendor_delivery_text_gmc, fourth_vendor_delivery_text_website, fourth_vendor_stock_text_website, fourth_vendor_price_date, fourth_vendor_stock,
                        fifth_vendor_product_id, fifth_vendor_name, fifth_vendor_price, fifth_vendor_final_price, fifth_vendor_shipping, fifth_vendor_extra_discount, fifth_vendor_product_url, fifth_vendor_source,
                        fifth_vendor_delivery_date, fifth_vendor_is_backorder, fifth_vendor_delivery_text_gmc, fifth_vendor_delivery_text_website, fifth_vendor_stock_text_website, fifth_vendor_price_date, fifth_vendor_stock,
                        percentage, second_percentage, assumed_map_price,
                        rt, rp, rp_variation, rp_variation_sell_price, rp_coupon, achieved_gp, rp_criteria, is_rp_calculated
                    FROM TempVendorPricing
                    WHERE
                        vendor_pricing_id = %s
                    LIMIT 1;
                """, (current_vendor_pricing_id,))
                pricing_data_for_history = this.fetchone()
                if pricing_data_for_history:
                    pricing_data_for_history_list = [
                        pricing_data_for_history[0], pricing_data_for_history[1], pricing_data_for_history[2], pricing_data_for_history[3], pricing_data_for_history[4], pricing_data_for_history[5], 
                        pricing_data_for_history[6], pricing_data_for_history[7], pricing_data_for_history[8], pricing_data_for_history[9], pricing_data_for_history[10], pricing_data_for_history[11], 
                        pricing_data_for_history[12], pricing_data_for_history[13], pricing_data_for_history[14], pricing_data_for_history[15], pricing_data_for_history[16], pricing_data_for_history[17], 
                        pricing_data_for_history[18], pricing_data_for_history[19], pricing_data_for_history[20], pricing_data_for_history[21], pricing_data_for_history[22], pricing_data_for_history[23], 
                        pricing_data_for_history[24], pricing_data_for_history[25], pricing_data_for_history[26], pricing_data_for_history[27], pricing_data_for_history[28], pricing_data_for_history[29], 
                        pricing_data_for_history[30], pricing_data_for_history[31], pricing_data_for_history[32], pricing_data_for_history[33], pricing_data_for_history[34], pricing_data_for_history[35], 
                        pricing_data_for_history[36], pricing_data_for_history[37], pricing_data_for_history[38], pricing_data_for_history[39], pricing_data_for_history[40], pricing_data_for_history[41], 
                        pricing_data_for_history[42], pricing_data_for_history[43], pricing_data_for_history[44], pricing_data_for_history[45], pricing_data_for_history[46], pricing_data_for_history[47], 
                        pricing_data_for_history[48], pricing_data_for_history[49], pricing_data_for_history[50], pricing_data_for_history[51], pricing_data_for_history[52], pricing_data_for_history[53], 
                        pricing_data_for_history[54], pricing_data_for_history[55], pricing_data_for_history[56], pricing_data_for_history[57], pricing_data_for_history[58], pricing_data_for_history[59], 
                        pricing_data_for_history[60], pricing_data_for_history[61], pricing_data_for_history[62], pricing_data_for_history[63], pricing_data_for_history[64], pricing_data_for_history[65], 
                        pricing_data_for_history[66], pricing_data_for_history[67], pricing_data_for_history[68], pricing_data_for_history[69], pricing_data_for_history[70], pricing_data_for_history[71], 
                        pricing_data_for_history[72], pricing_data_for_history[73], pricing_data_for_history[74], pricing_data_for_history[75], pricing_data_for_history[76], pricing_data_for_history[77], 
                        pricing_data_for_history[78], pricing_data_for_history[79], pricing_data_for_history[80], pricing_data_for_history[81], pricing_data_for_history[82], pricing_data_for_history[83], 
                        pricing_data_for_history[84], pricing_data_for_history[85], pricing_data_for_history[86], pricing_data_for_history[87], pricing_data_for_history[88], pricing_data_for_history[89], 
                        pricing_data_for_history[90], pricing_data_for_history[91], pricing_data_for_history[92], pricing_data_for_history[93], pricing_data_for_history[94], pricing_data_for_history[95], 
                        pricing_data_for_history[96], pricing_data_for_history[97], pricing_data_for_history[98], pricing_data_for_history[99], pricing_data_for_history[100], pricing_data_for_history[101], 
                        pricing_data_for_history[102], pricing_data_for_history[103], pricing_data_for_history[104], pricing_data_for_history[105], pricing_data_for_history[106], pricing_data_for_history[107], 
                        pricing_data_for_history[108], pricing_data_for_history[109], pricing_data_for_history[110], pricing_data_for_history[111], pricing_data_for_history[112]
                    ]
                else: pricing_data_for_history_list = []
                # check and insert/update ranking in history table
                savePricingHistory(last_updated, vendor_id, update_query, update_values, pricing_data_for_history_list)
    except mysql.connector.Error as e:
        logger.debug(f"MySQL ERROR saveRanks() >> {e}")
    finally:
        if conn.is_connected():
            this.close()
            conn.close()

# check and insert/update ranking in history table
def savePricingHistory(data, vendor_id, update_query, update_values, pricing_data_for_history_list):
    try:
        if vendor_id == 10021 or vendor_id == 10024:
            conn = mysql.connector.connect(host=HOST2, database=DB2, user=USER2, password=PASS2)
        else:
            conn = mysql.connector.connect(host=HOST3, database=DB3, user=USER3, password=PASS3)
        
        if conn.is_connected():
            this = conn.cursor()
            pricing_history_table = f"z_{vendor_id}_VendorPricing"
            vendor_product_id, vendorprice_date, source, product_condition = data

            this.execute(f"""
                SELECT vendor_pricing_id
                FROM {pricing_history_table}
                WHERE vendor_product_id = %s
                  AND vendorprice_date = %s
                  AND source = %s
                  AND product_condition = %s
                ORDER BY vendor_pricing_id DESC
                LIMIT 1
            """, (vendor_product_id, vendorprice_date, source, product_condition))

            result = this.fetchone()
            if result:
                vendor_pricing_id = result[0]
                this.execute(f"""
                    UPDATE {pricing_history_table}
                    SET
                        first_vendor_product_id = NULL, first_vendor_name = NULL, first_vendor_price = NULL, first_vendor_final_price = NULL, first_vendor_shipping = NULL,
                        first_vendor_extra_discount = NULL, first_vendor_product_url = NULL, first_vendor_source = NULL, first_vendor_delivery_date = NULL,
                        first_vendor_is_backorder = 'no', first_vendor_delivery_text_gmc = NULL, first_vendor_delivery_text_website = NULL, first_vendor_stock_text_website = NULL,
                        first_vendor_price_date = NULL, first_vendor_stock = NULL, second_vendor_product_id = NULL, second_vendor_name = NULL, second_vendor_price = NULL,
                        second_vendor_final_price = NULL, second_vendor_shipping = NULL, second_vendor_extra_discount = NULL, second_vendor_product_url = NULL,
                        second_vendor_source = NULL, second_vendor_delivery_date = NULL, second_vendor_is_backorder = 'no', second_vendor_delivery_text_gmc = NULL,
                        second_vendor_delivery_text_website = NULL, second_vendor_stock_text_website = NULL, second_vendor_price_date = NULL, second_vendor_stock = NULL,
                        third_vendor_product_id = NULL, third_vendor_name = NULL, third_vendor_price = NULL, third_vendor_final_price = NULL, third_vendor_shipping = NULL,
                        third_vendor_extra_discount = NULL, third_vendor_product_url = NULL, third_vendor_source = NULL, third_vendor_delivery_date = NULL,
                        third_vendor_is_backorder = 'no', third_vendor_delivery_text_gmc = NULL, third_vendor_delivery_text_website = NULL, third_vendor_stock_text_website = NULL,
                        third_vendor_price_date = NULL, third_vendor_stock = NULL, fourth_vendor_product_id = NULL, fourth_vendor_name = NULL, fourth_vendor_price = NULL,
                        fourth_vendor_final_price = NULL, fourth_vendor_shipping = NULL, fourth_vendor_extra_discount = NULL, fourth_vendor_product_url = NULL,
                        fourth_vendor_source = NULL, fourth_vendor_delivery_date = NULL, fourth_vendor_is_backorder = 'no', fourth_vendor_delivery_text_gmc = NULL,
                        fourth_vendor_delivery_text_website = NULL, fourth_vendor_stock_text_website = NULL, fourth_vendor_price_date = NULL, fourth_vendor_stock = NULL,
                        fifth_vendor_product_id = NULL, fifth_vendor_name = NULL, fifth_vendor_price = NULL, fifth_vendor_final_price = NULL, fifth_vendor_shipping = NULL,
                        fifth_vendor_extra_discount = NULL, fifth_vendor_product_url = NULL, fifth_vendor_source = NULL, fifth_vendor_delivery_date = NULL,
                        fifth_vendor_is_backorder = 'no', fifth_vendor_delivery_text_gmc = NULL, fifth_vendor_delivery_text_website = NULL, fifth_vendor_stock_text_website = NULL,
                        fifth_vendor_price_date = NULL, fifth_vendor_stock = NULL, percentage = NULL, second_percentage = NULL, assumed_map_price = NULL, is_rp_calculated = '0'
                    WHERE vendor_pricing_id = %s
                """, (vendor_pricing_id,))
                conn.commit()

                if this.rowcount == 1:
                    logger.debug(f"Ranks are set NULL for vendor_pricing_id ({vendor_pricing_id}) in history table.")

                # Update the ranking data
                update_query = update_query.replace('TempVendorPricing', pricing_history_table)

                # Replace WHERE clause and keep placeholder %s
                if 'vendor_pricing_id = %s' not in update_query:
                    update_query = update_query.split("WHERE")[0] + " WHERE vendor_pricing_id = %s"

                update_values = list(update_values) + [vendor_pricing_id]

                this.execute(update_query, tuple(update_values))
                conn.commit()

                if this.rowcount == 1:
                    logger.debug(f"Pricing data updated for vendor_pricing_id ({vendor_pricing_id}) in history table.")
            else:
                if len(pricing_data_for_history_list) > 0:
                    # Insert data if not found
                    insert_query = f"""
                        INSERT INTO {pricing_history_table} (
                            vendor_product_id, vendorprice_price, vendorprice_finalprice, vendorprice_date, vendorprice_shipping, vendorprice_return,
                            vendorprice_stock, vendorprice_stock_text, vendorprice_stockdate, vendorprice_isbackorder, is_active, vendorprice_offers,
                            vendorprice_delivery_date, delivery_text, vendorprice_extra_discount, currency, rank, source, shipping_time, product_condition,
                            sales, average_price, is_found, is_suspicious, marketing_message, competitor_count, same_price_vendor_count,
                            first_vendor_product_id, first_vendor_name, first_vendor_price, first_vendor_final_price, first_vendor_shipping,
                            first_vendor_extra_discount, first_vendor_product_url, first_vendor_source, first_vendor_delivery_date,
                            first_vendor_is_backorder, first_vendor_delivery_text_gmc, first_vendor_delivery_text_website,
                            first_vendor_stock_text_website, first_vendor_price_date, first_vendor_stock,
                            second_vendor_product_id, second_vendor_name, second_vendor_price, second_vendor_final_price,
                            second_vendor_shipping, second_vendor_extra_discount, second_vendor_product_url, second_vendor_source,
                            second_vendor_delivery_date, second_vendor_is_backorder, second_vendor_delivery_text_gmc,
                            second_vendor_delivery_text_website, second_vendor_stock_text_website, second_vendor_price_date,
                            second_vendor_stock, third_vendor_product_id, third_vendor_name, third_vendor_price, third_vendor_final_price,
                            third_vendor_shipping, third_vendor_extra_discount, third_vendor_product_url, third_vendor_source,
                            third_vendor_delivery_date, third_vendor_is_backorder, third_vendor_delivery_text_gmc,
                            third_vendor_delivery_text_website, third_vendor_stock_text_website, third_vendor_price_date,
                            third_vendor_stock, fourth_vendor_product_id, fourth_vendor_name, fourth_vendor_price,
                            fourth_vendor_final_price, fourth_vendor_shipping, fourth_vendor_extra_discount, fourth_vendor_product_url,
                            fourth_vendor_source, fourth_vendor_delivery_date, fourth_vendor_is_backorder,
                            fourth_vendor_delivery_text_gmc, fourth_vendor_delivery_text_website, fourth_vendor_stock_text_website,
                            fourth_vendor_price_date, fourth_vendor_stock, fifth_vendor_product_id, fifth_vendor_name,
                            fifth_vendor_price, fifth_vendor_final_price, fifth_vendor_shipping, fifth_vendor_extra_discount,
                            fifth_vendor_product_url, fifth_vendor_source, fifth_vendor_delivery_date, fifth_vendor_is_backorder,
                            fifth_vendor_delivery_text_gmc, fifth_vendor_delivery_text_website, fifth_vendor_stock_text_website,
                            fifth_vendor_price_date, fifth_vendor_stock, percentage, second_percentage, assumed_map_price,
                            rt, rp, rp_variation, rp_variation_sell_price, rp_coupon, achieved_gp, rp_criteria, is_rp_calculated
                        ) VALUES ({','.join(['%s'] * len(pricing_data_for_history_list))})
                    """
                    this.execute(insert_query, tuple(pricing_data_for_history_list))
                    conn.commit()

                    if this.rowcount == 1:
                        logger.debug(f"Pricing data inserted for vendor_pricing_id ({this.lastrowid}) in history table.")
    except mysql.connector.Error as e:
        logger.debug(f"MySQL ERROR savePricingHistory() >> {e}")
    finally:
        if conn.is_connected():
            this.close()
            conn.close()

# Get products to find vendor ranking
def products(vendor_id, product_id):
    try:
        conn = mysql.connector.connect(host=HOST, database=DB, user=USER, password=PASS)
        if conn.is_connected():
            this = conn.cursor()
            this.execute(f"""
                SELECT
                    DISTINCT ProductVendor.vendor_product_id,
                    ProductVendor.vendor_id,
                    ProductVendor.product_id
                FROM Product
                INNER JOIN ProductVendor ON ProductVendor.product_id = Product.product_id
                INNER JOIN Vendor ON Vendor.vendor_id = ProductVendor.vendor_id
                WHERE
                    ProductVendor.vendor_id = {vendor_id}
                    AND Product.product_id = {product_id}
            """)
            result = this.fetchall()
            if len(result) > 0:
                return result
            else:
                return []
    except mysql.connector.Error as e:
        logger.warning(f"MySQL ERROR products() >> {e}")
    finally:
        if conn.is_connected():
            this.close()
            conn.close()

# start making ranking of the products
def commence(vendorID, productID):
    start = time.perf_counter()
    logger.debug("""
    ------ Starting evaluating competitors ranking of the product ---------
    """)

    vendorsProducts = products(vendorID, productID)
    if len(vendorsProducts) > 0:
        for vendorProduct in vendorsProducts:
            saveRanks(vendorProduct)
    else:
        logger.debug(f'Not found any product (PID: {productID}) to evaluate ranking.')

    finish = time.perf_counter()
    logger.debug(f'Finished making ranking of the product in {round(finish - start, 2)} second(s)')
    