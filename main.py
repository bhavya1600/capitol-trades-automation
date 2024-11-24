import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options  # Added import for Options
from datetime import date, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.cloud import storage
import io
from selenium.webdriver.firefox.service import Service

# # Retrieve Job-defined env vars
# TASK_INDEX = os.getenv("CLOUD_RUN_TASK_INDEX", 0)
# TASK_ATTEMPT = os.getenv("CLOUD_RUN_TASK_ATTEMPT", 0)

service = Service(log_path='geckodriver.log')

# Configure Firefox to run in headless mode
options = Options()
options.headless = True

# Initialize the Firefox driver with the headless option
driver = webdriver.Firefox(service=service, options=options)

# driver.fullscreen_window()

# Navigate to the webpage
driver.get("https://www.capitoltrades.com/trades")

# Cookie Banner
try:
        # Wait for the cookie banner to appear and accept it
        cookie_accept_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Accept") or contains(text(), "I Agree")]'))
        )
        cookie_accept_button.click()
        print("Cookie banner accepted.")
except:
    # If the cookie banner is not present, proceed
    print("No cookie banner found or already accepted.")

    
# try:
#     # Wait for the dropdown to be clickable and click it to open the options
#     dropdown = WebDriverWait(driver, 10).until(
#         EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.dropdown-group.field--per-page .dropdown-selector'))
#     )
#     dropdown.click()
#     print("Dropdown clicked to open options.")

#     # Wait for the dropdown content to appear
#     dropdown_content = WebDriverWait(driver, 10).until(
#         EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.dropdown-content.flavour--minimal.bs.anim-appear-from-top'))
#     )
#     print("Dropdown content is visible.")

#     # Wait for the '96' option's label to be clickable within the dropdown content and click it
#     option_96_label = WebDriverWait(driver, 10).until(
#         EC.element_to_be_clickable((
#             By.XPATH, 
#             '//div[contains(@class, "dropdown-content")]//label[contains(@class, "q-choice-wrapper")]//span[@class="q-label per-page" and text()="96"]/..'
#         ))
#     )
#     option_96_label.click()
#     print("Selected '96' from the dropdown.")

#     # Optionally, wait for the table to refresh after selecting '96'
#     # This ensures that the table reflects the new number of entries per page
#     WebDriverWait(driver, 10).until(
#         EC.staleness_of(driver.find_element(By.TAG_NAME, 'tbody'))
#     )
#     WebDriverWait(driver, 10).until(
#         EC.presence_of_element_located((By.TAG_NAME, 'tbody'))
#     )
#     print("Table refreshed after selecting '96'.")

# except Exception as e:
#     print(f"Could not select '96' from the dropdown: {e}")

# Initialize an empty list to store the data
data = []

pages = 5

for i in range(5):
    
    # Wait for the table to load
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, 'tbody'))
    )

    # Find the table body
    table_body = driver.find_element(By.TAG_NAME, 'tbody')

    # Find all rows in the table
    rows = table_body.find_elements(By.TAG_NAME, 'tr')



    # Loop over each row
    for row in rows:
        # Get all cells in the row
        cells = row.find_elements(By.TAG_NAME, 'td')
        
        # Skip rows that do not have enough cells (e.g., "Goto trade detail page")
        if len(cells) < 9:
            continue
        
        # Extract text from each cell
        politician_info = cells[0].text.split('\n')
        politician_name = politician_info[0]
        trade_issuer = cells[1].text.strip().split('\n')[0]
        trade_issuer_alias = cells[1].text.strip().split('\n')[1]
        published = cells[2].text.strip().replace('\n', ' ')

        if 'Yesterday' in published:
            yesterday = date.today() - timedelta(days=1)
            published = yesterday.strftime('%d %b %Y')
        elif 'Today' in published:
            published = date.today().strftime('%d %b %Y')
        else:
            published = published

        traded = cells[3].text.strip().replace('\n', ' ')

        filed_after = cells[4].text.strip().replace('\n', ' ')
        filed_after_split = filed_after.split(' ')
        filed_after = f"{filed_after_split[1]} {filed_after_split[0]}"
        
        owner = cells[5].text.strip()
        trade_type = cells[6].text.strip()
        size = cells[7].text.strip()
        price = cells[8].text.strip()
        
        # Append the data to the list
        data.append({
            'Politician': politician_name,
            'Trade Issuer': trade_issuer,
            'Trade Issuer Alias': trade_issuer_alias,
            'Published': published,
            'Traded': traded,
            'Filed After': filed_after,
            'Owner': owner,
            'Type': trade_type,
            'Size': size,
            'Price': price
        })
    
    
    try:
        # Wait for the "Next Page" button to be clickable
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[aria-label="Go to next page"]'))
        )
        next_button.click()
        print("Navigated to the next page.")
    except Exception as e:
        print(f"Could not click the next page button: {e}")
        break  # Exit the loop if unable to navigate to the next page

def upload_to_gcs(bucket_name, data, destination_blob_name, is_string=True):
    storage_client = storage.Client(project='tough-shelter-333216')
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    if is_string:
        blob.upload_from_string(data, content_type='text/csv')
    else:
        blob.upload_from_filename(data, content_type='text/csv')


def download_from_gcs(bucket_name, source_blob_name):
    storage_client = storage.Client(project='tough-shelter-333216')
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)

    if blob.exists(storage_client):
        data = blob.download_as_text()
        df = pd.read_csv(io.StringIO(data))
        return df
    else:
        return None

bucket_name = 'tradehog'

# Create a DataFrame
df = pd.DataFrame(data)
df.reset_index(drop=True, inplace=True)
df_string = df.to_csv(index=False)
upload_to_gcs(bucket_name, df_string, 'trades_new.csv', is_string=True)
# Define the path for trades.csv
trades_csv_blob = 'trades.csv'


# Check if trades.csv exists
existing_trades_df = download_from_gcs(bucket_name, trades_csv_blob)

if existing_trades_df is not None:
        existing_trades_df.reset_index(drop=True, inplace=True)
        # 'trades.csv' exists. Proceed to merge and find differences.
        print(f'{trades_csv_blob} already exists, finding differences and merging')
        # Check if 'trades.csv' exists in GCS
        new_df = download_from_gcs(bucket_name, 'trades_new.csv')
        # Merge existing trades with new trades
        diff_df = existing_trades_df.merge(new_df, how='outer', indicator=True)

        # Identify rows only in new_trades_df
        only_in_new = diff_df[diff_df['_merge'] == 'right_only'].drop('_merge', axis=1)

        # Convert the differences to CSV
        only_in_new_csv = only_in_new.to_csv(index=False)

        # Upload 'trades_diff.csv' to GCS
        upload_to_gcs(bucket_name, only_in_new_csv, 'trades_diff.csv', is_string=True)

        # Update 'trades.csv' in GCS with the new trades
        updated_trades_csv = new_df.to_csv(index=False)
        upload_to_gcs(bucket_name, updated_trades_csv, trades_csv_blob, is_string=True)

else:
        # 'trades.csv' does not exist. Initialize it with the new trades.
        print(f"{trades_csv_blob} doesn't exist, creating it now")
        # Upload 'trades.csv' to GCS
        upload_to_gcs(bucket_name, df_string, trades_csv_blob, is_string=True)

        # Also upload 'trades_new.csv' as it's the first set of trades
        # (Already uploaded above, but you can choose to handle it differently if needed)
        # upload_to_gcs(BUCKET_NAME, new_trades_csv, 'trades_new.csv', is_string=True)

        # The differences are the new trades themselves
        only_in_new = df.copy(deep=True)


# Display the DataFrame
print(only_in_new)

# Close the driver
driver.quit()


# Email configuration
SMTP_SERVER = 'smtp.gmail.com'  # For Gmail. Change if using another provider.
SMTP_PORT = 587
EMAIL_ADDRESS = 'mitali21bday@gmail.com'  # Replace with your email
EMAIL_PASSWORD = 'kksg ligc xnkc gepo'  # Replace with your email password or app-specific password
RECIPIENT_EMAIL = 'bhavya1600@gmail.com'  # Replace with recipient's email
EMAIL_SUBJECT = "Today's Capitol Trades"
EMAIL_BODY = 'Please find below the latest trades data for today:'

def highlight_rows(row):
    """
    Apply background color to entire row based on the 'Type' column.
    
    Parameters:
        row (pd.Series): A row of the DataFrame.
        
    Returns:
        list: A list of CSS styles for each cell in the row.
    """
    if row['Type'] == 'SELL':
        # Mild Yellow
        return ['background-color: #FFF9C4'] * len(row)
    elif row['Type'] == 'BUY':
        # Mild Green
        return ['background-color: #C8E6C9'] * len(row)
    else:
        # No styling
        return [''] * len(row)


def html(df, content_available=False):
    if content_available:
    # Optional: Format the DataFrame (e.g., handle NaN values)
        df.fillna('N/A', inplace=True)
        # Create a Styler object and apply the row highlighting
        # styled_df = df.style.apply(highlight_rows, axis=1)

        # Optionally, set table classes and attributes
        # styled_df = styled_df.set_td_classes('table table-striped').set_table_attributes('style="width:100%"')

        # Convert the styled DataFrame to HTML
        html_table = df.render()
        # Convert DataFrame to HTML table
        # html_table = df.to_html(index=False, justify='left', classes='table table-striped')

        # Add some basic styling (optional)
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{EMAIL_SUBJECT}</title>
            <style>
                /* General Styles */
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 0;
                }}
                .email-container {{
                    max-width: 800px;
                    margin: 20px auto;
                    background-color: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    text-align: center;
                    padding-bottom: 20px;
                    border-bottom: 1px solid #dddddd;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    color: #333333;
                }}
                .content {{
                    padding: 20px 0;
                }}
                .content p {{
                    font-size: 16px;
                    color: #555555;
                    line-height: 1.5;
                }}
                /* Table Styles */
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                th, td {{
                    padding: 12px 15px;
                    text-align: left;
                }}
                th {{
                    background-color: #4C44F0;
                    color: white;
                    font-size: 16px;
                    border: 1px solid #dddddd;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                tr:hover {{
                    background-color: #f1f1f1;
                }}
                td {{
                    border: 1px solid #dddddd;
                    color: #555555;
                    font-size: 14px;
                }}
                /* Footer Styles */
                .footer {{
                    text-align: center;
                    padding-top: 20px;
                    border-top: 1px solid #dddddd;
                    color: #999999;
                    font-size: 12px;
                }}
                /* Responsive Design */
                @media only screen and (max-width: 600px) {{
                    .email-container {{
                        padding: 15px;
                    }}
                    th, td {{
                        padding: 10px;
                    }}
                    .header h1 {{
                        font-size: 20px;
                    }}
                    .content p {{
                        font-size: 14px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>Found {len(diff_df)} New Trades!</h1>
                </div>
                <div class="content">
                    <p>Dear Bhavya,</p>
                    <p>Please find below the latest trades data:</p>
                    {html_table}
                    <p>Best regards,<br>Your Trade Hog</p>
                </div>
                <div class="footer">
                    &copy; {pd.Timestamp.now().year} Trade Hog. All rights reserved.
                </div>
            </div>
        </body>
        </html>
        """
        return html_content
    
    else:
        html_content_no_trades = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>No New Trades to Report</title>
            <style>
                /* General Styles */
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 0;
                }}
                .email-container {{
                    max-width: 600px;
                    margin: 40px auto;
                    background-color: #ffffff;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    text-align: center;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #dddddd;
                }}
                .header h2 {{
                    margin: 0;
                    font-size: 24px;
                    color: #333333;
                }}
                .content {{
                    padding: 20px 0;
                    text-align: center;
                }}
                .content p {{
                    font-size: 16px;
                    color: #555555;
                    line-height: 1.6;
                    margin: 10px 0;
                }}
                .footer {{
                    text-align: center;
                    padding-top: 20px;
                    border-top: 2px solid #dddddd;
                    color: #999999;
                    font-size: 12px;
                }}
                /* Responsive Design */
                @media only screen and (max-width: 600px) {{
                    .email-container {{
                        padding: 20px;
                    }}
                    .header h2 {{
                        font-size: 20px;
                    }}
                    .content p {{
                        font-size: 14px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h2>No New Trades</h2>
                </div>
                <div class="content">
                    <p>Dear Bhavya,</p>
                    <p>No new trades to report today.</p>
                    <p>Best Regards,<br>Your Trade Hog</p>
                </div>
                <div class="footer">
                    &copy; {current_year} Your Trade Hog. All rights reserved.
                </div>
            </div>
        </body>
        </html>
        """.format(current_year=date.today().year)
        return html_content_no_trades


# -------------------
# Function to Send Email
# -------------------

def send_email(html_content):
    # Create a multipart message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = EMAIL_SUBJECT
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = RECIPIENT_EMAIL

        # Attach the HTML content
    mime_text = MIMEText(html_content, 'html')
    msg.attach(mime_text)

    # Connect to SMTP server and send email
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Secure the connection
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

if len(only_in_new) > 0:
    content_available = True
    print("New trades found. Sending email...")
else:
    content_available = False
    print("No new trades found. Sending email with no content...")

html_content = html(only_in_new, content_available)
send_email(html_content)

