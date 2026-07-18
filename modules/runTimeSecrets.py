import requests

url = "https://growth.matridtech.net/api/database-api"

headers = {
    "Authorization": "Bearer YOUR_ACCESS_TOKEN",  # if needed
    "Accept": "application/json"
}
# Make the GET request
response = requests.get(url, headers=headers)

# Check for success
if response.status_code == 200:
    data = response.json()  # Parse JSON response
    live_db = data.get('live_db', {})
    af_history_db = data.get('af_history_db', {})
    other_vendor_history_db = data.get('other_vendor_history_db', {})

    # Assign to your variables
    HOST = live_db.get('host')
    DB   = live_db.get('db_name')
    USER = live_db.get('user_name')
    PASS = live_db.get('password')

    # Connect to the database  VendorPricing DB - AF/HP
    HOST2 = af_history_db.get('host')
    DB2 = af_history_db.get('db_name')
    USER2 = af_history_db.get('user_name')
    PASS2 = af_history_db.get('password')
    
    # MSP Live Vendor Specific VendorPricing DB - NON AF/HP
    HOST3 = other_vendor_history_db.get('host')
    DB3 = other_vendor_history_db.get('db_name')
    USER3 = other_vendor_history_db.get('user_name')
    PASS3 = other_vendor_history_db.get('password')

else:
    print("Error:", response.status_code, response.text)