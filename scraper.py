import requests
import json
import os.path
import os
import sqlite3
import argparse
import time
import cloudscraper
import re

# ArgParse
parser = argparse.ArgumentParser(description='Vinted & Depop Scraper/Downloader. Default downloads Vinted')
parser.add_argument('--depop','-d',dest='Depop', action='store_true', help='Download Depop data.')
parser.add_argument('--private_msg','-p',dest='priv_msg', action='store_true', help='Download images from private messages from Vinted')
parser.add_argument('--user_id','-u',dest='user_id', action='store', help='Your own userid', required=False)
parser.add_argument('--session_id','-s',dest='session_id', action='store', help='Session id cookie for Vinted', required=False)
parser.add_argument('--disable-file-download','-n',dest='disable_file_download', action='store_true', help='Disable file download (Currently only working for depop)', required=False)
parser.add_argument('--sold_items','-g',dest='sold_items', action='store_true', help='Also download sold items (depop)', required=False)
parser.add_argument('--start_from','-b',dest='start_from', action='store', help='Begin from a specific item (depop)', required=False)
args = parser.parse_args()

# create downlods folders
if not os.path.exists('downloads'):
    os.makedirs('downloads')

try:
    os.mkdir(f"downloads/Avatars/")
except OSError:
    print("Creation of the directory failed or the folder already exists ")


#database
sqlite_file = 'data.sqlite'
conn = sqlite3.connect(sqlite_file)
c = conn.cursor()
# Create Data table if not exists
c.execute('''CREATE TABLE IF NOT EXISTS Data
             (ID, User_id, Sold, Gender, Category, subcategory, size, State, Brand, Colors, Price, Image, Images, Description, Title, Platform)''')
c.execute('''CREATE TABLE IF NOT EXISTS Depop_Data
             (ID, User_id, Sold, Gender, Category, subcategory, size, State, Brand, Colors, Price, Image, Description, Title, Platform, Address, discountedPriceAmount, dateUpdated)''')
# Create Users table if not exists
c.execute('''CREATE TABLE IF NOT EXISTS Users
             (Username, User_id, Gender, Given_item_count, Taken_item_count, Followers_count, Following_count, Positive_feedback_count, Negative_feedback_count, Feedback_reputation, Avatar, Created_at, Last_loged_on_ts, City_id, City, Country_title, Verification_email, Verification_facebook, Verification_google, Verification_phone, Platform)''')
c.execute('''CREATE TABLE IF NOT EXISTS Depop_Users
             (Username, User_id, bio, first_name, followers, following, initials, items_sold, last_name, last_seen, Avatar, reviews_rating, reviews_total, verified, website)''')
c.execute('''CREATE TABLE IF NOT EXISTS Vinted_Messages
             (thread_id, from_user_id, to_user_id, msg_id, body, photos)''')
conn.commit()


def vinted_session():
    s = cloudscraper.create_scraper()
    s.headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en',
        'DNT': '1',
        'Connection': 'keep-alive',
        'TE': 'Trailers',
    }
    req = s.get("https://www.vinted.nl/")
    # csrfToken = req.text.split('<meta name="csrf-token" content="')[1].split('"')[0]
    # s.headers['X-CSRF-Token'] = csrfToken
    return s

def download_priv_msg(session_id, user_id):
    s = cloudscraper.create_scraper()
    s.headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en',
        'DNT': '1',
        'Connection': 'keep-alive',
        'TE': 'Trailers',
        'Cookie': f"_vinted_fr_session={session_id};"
    }
    print(session_id)
    data = s.get(f"https://www.vinted.nl/api/v2/users/{user_id}/msg_threads")
    if data.status_code ==403:
        # Access denied
        print(f"Error: Access Denied\nCan't get content from 'https://www.vinted.nl/api/v2/users/{user_id}/msg_threads'")
        exit(1)
    data = data.json()
    try:
        os.mkdir(f"downloads/Messages/")
    except OSError:
        print("Creation of the directory failed or the folder already exists ")
    if not "msg_threads" in data:
        print("Error: Can't find any messages.\nPlease make sure you entered the sessionid correctly")
        exit(1)
    for msg_threads in data['msg_threads']:
        id = msg_threads['id']
        msg_data = s.get(f"https://www.vinted.nl/api/v2/users/{user_id}/msg_threads/{id}").json()

        thread_id = msg_data['msg_thread']['id']
        for message in msg_data['msg_thread']['messages']:
            try:
                photo_data = message['entity']['photos']
            except:
                continue
            if len(photo_data) > 0:
                try:
                    os.mkdir(f"downloads/Messages/{message['entity']['user_id']}")
                except OSError:
                    print ("Creation of the directory failed or the folder already exists ")

                from_user_id = message['entity']['user_id']
                msg_id = message['entity']['id']
                body = message['entity']['body']
                photo_list = []
                for photo in message['entity']['photos']:
                    req = requests.get(photo['full_size_url'])

                    filepath = f"downloads/Messages/{from_user_id}/{photo['id']}.jpeg"
                    photo_list.append(filepath)
                    if not os.path.isfile(filepath):
                        print(photo['id'])
                        with open(filepath, 'wb') as f:
                            f.write(req.content)
                        print(f"Image saved to {filepath}")
                    else:
                        print('File already exists, skipped.')
                if int(from_user_id) == int(user_id):
                    to_user_id = msg_data['msg_thread']['opposite_user']['id']
                else:
                    to_user_id = user_id
                # Save to DB

                params = (thread_id, from_user_id, to_user_id, msg_id, body, str(photo_list))
                c.execute(
                    "INSERT INTO Vinted_Messages(thread_id, from_user_id, to_user_id, msg_id, body, photos)VALUES (?,?,?,?,?,?)",
                    params)
                conn.commit()

def get_all_items(s, USER_ID, total_pages, items):
    for page in range(int(total_pages)):
        page +=1
        url = f'https://www.vinted.nl/api/v2/users/{USER_ID}/items?page={page}&per_page=200000'
        r = s.get(url).json()
        print(f"Fetching page {page+1}/{r['pagination']['total_pages']}")
        items.extend(r['items'])

def download_vinted_data(userids, s):
    Platform = "Vinted"
    for USER_ID in userids:
        USER_ID = USER_ID.strip()
        # Get user profile data
        url = f"https://www.vinted.nl/api/v2/users/{USER_ID}"
        r = s.get(url)
        if r.status_code == 200:
            jsonresponse = r.json()
            data = jsonresponse['user']
            #get data
            username = data['login']
            try:
                gender = data['gender']
            except KeyError:
                gender = ""
            given_item_count = data['given_item_count']
            taken_item_count = data['taken_item_count']
            followers_count = data['followers_count']
            following_count = data['following_count']
            positive_feedback_count = data['positive_feedback_count']
            negative_feedback_count = data['negative_feedback_count']
            feedback_reputation = data['feedback_reputation']
            try:
                created_at = data['created_at']
            except KeyError:
                created_at = ""
            last_loged_on_ts = data['last_loged_on_ts']
            city_id = data['city_id']
            city = data['city']
            country_title = data['country_title']
            verification_email = data['verification']['email']['valid']
            verification_facebook = data['verification']['facebook']['valid']
            verification_google = data['verification']['google']['valid']
            verification_phone = data['verification']['phone']['valid']
            
            USER_ID = USER_ID.strip('\n')

            vinted_user_path = 'downloads/' + str(username) + ' (' + str(USER_ID) +') /'
            
            if data['photo']:
                photo = data['photo']['full_size_url']
                photo_id = data['photo']['id']
                try:
                    os.mkdir(f"downloads/Avatars/")
                except OSError:
                    print ("Creation of the directory failed or the folder already exists ")
                req = requests.get(photo)
                filepath = f'downloads/Avatars/{username}_{photo_id}.jpeg'
                if not os.path.isfile(filepath):
                    print(photo_id)
                    with open(filepath, 'wb') as f:
                        f.write(req.content)
                    print(f"Avatar saved to {filepath}")
                else:
                    print('File already exists, skipped.')
                params = (
                    username, USER_ID, gender, given_item_count, taken_item_count, followers_count, following_count,
                    positive_feedback_count, negative_feedback_count, feedback_reputation, filepath,
                    last_loged_on_ts, city_id, city, country_title, verification_email, verification_google,
                    verification_facebook, verification_phone)
                c.execute(
                    "INSERT INTO Users(Username, User_id, Gender, Given_item_count, Taken_item_count, Followers_count, Following_count, Positive_feedback_count, Negative_feedback_count, Feedback_reputation, Avatar, Last_loged_on_ts, City_id, City, Country_title, Verification_email, Verification_facebook, Verification_google, Verification_phone)VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    params)
                conn.commit()

            else:
                # If no avatar put empty string in DB
                Avatar = ""
                params = (
                    username, USER_ID, gender, given_item_count, taken_item_count, followers_count, following_count,
                    positive_feedback_count, negative_feedback_count, feedback_reputation, Avatar,
                    last_loged_on_ts, city_id, city, country_title, verification_email, verification_google, verification_facebook,
                    verification_phone)
                c.execute(
                    "INSERT INTO Users(Username, User_id, Gender, Given_item_count, Taken_item_count, Followers_count, Following_count, Positive_feedback_count, Negative_feedback_count, Feedback_reputation, Avatar, Last_loged_on_ts, City_id, City, Country_title, Verification_email, Verification_facebook, Verification_google, Verification_phone)VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    params)
                conn.commit()

            url = f'https://www.vinted.nl/api/v2/users/{USER_ID}/items?page=1&per_page=200000'
            print('ID=' + str(USER_ID))

            r = s.get(url)
            items = []
            print(f"Fetching page 1/{r.json()['pagination']['total_pages']}")
            items.extend(r.json()['items'])
            # products = jsonresponse['items']
            if r.json()['pagination']['total_pages'] > 1:
                print(f"User has more than {len(items)} items. fetching next page....")
                get_all_items(s, USER_ID, r.json()['pagination']['total_pages'], items)
            products = items
            print(f"Total items: {len(products)}")
            if r.status_code == 200:
                # print(jsonresponse)

                if products:
                    # Download all products
                    try:
                        os.mkdir(vinted_user_path)
                    except OSError:
                        print ("Creation of the directory %s failed or the folder already exists " % vinted_user_path)
                    else:
                        print ("Successfully created the directory %s " % vinted_user_path)
                    for product in products:
                            img = product['photos']
                            ID = product['id']
                            User_id = product['user_id']
                            description = product['description']
                            try:
                                Gender = product['user']['gender']
                            except KeyError:
                                Gender = ""
                            Category = product['catalog_id']
                            size = product['size']
                            State = product['status']
                            Brand = product['brand']
                            Colors = product['color1']
                            Price = product['price']
                            Price = f"{Price['amount']} {Price['currency_code']}"
                            Images = product['photos']
                            title = product['title']
                            
                            
                            filename = re.sub(r'[\\/*?:"<>|]',"-", title)
                            
                            vinted_product_path = vinted_user_path + str(filename) + " (" + str(ID) + ')/'
                            try:
                                os.mkdir(vinted_product_path)
                            except OSError:
                                print ("Creation of the directory %s failed or the folder already exists " % vinted_product_path)
                            else:
                                print ("Successfully created the directory %s " % vinted_product_path)
                            
                            
                            vinted_product_file_path = vinted_product_path + 'product_info.txt'
                            with open(vinted_product_file_path, 'w', encoding="UTF-8") as product_file:
                                product_info = {
                                    "id": ID,
                                    "title": title,
                                    "description": description + '\n-----------',
                                    "size": size,
                                    "price": Price + product["currency"],
                                    "status": State,
                                    "brand": Brand,
                                    "created": product["created_at_ts"],
                                    "created_at": product["created_at"],
                                    "updated": product["updated_at_ts"],
                                    "user_updated": product["user_updated_at_ts"]
                                    }
                                    
                                for key, value in product_info.items(): 
                                    product_file.write('%s: %s\n' % (key, value))

                            #print(img)
                            if Images:
                                for images in img:
                                    full_size_url = images['full_size_url']
                                    img_name = images['high_resolution']['id']
                                    #print(img_name)
                                    filepath = vinted_product_path + img_name +'.jpeg'
                                    if not os.path.isfile(filepath):
                                        #print(full_size_url)
                                        req = requests.get(full_size_url)
                                        params = (ID, User_id, Gender, Category, size, State, Brand, Colors, Price, filepath, description, title, Platform)
                                        c.execute("INSERT INTO Data(ID, User_id, Gender, Category, size, State, Brand, Colors, Price, Images, description, title, Platform)VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", params)
                                        conn.commit()
                                        with open(filepath, 'wb') as f:
                                            f.write(req.content)
                                        print(f"Image saved to {filepath}")
                                    else:
                                        print('File already exists, skipped.')
                if not products:
                    print('User has no products')
            elif r.status_code == 429:
                print(f"Ratelimit waiting {r.headers['Retry-After']} seconds...")
                limit = round(int(r.headers['Retry-After']) / 2)
                for i in range(limit, 0, -1):
                    print(f"{i}", end="\r", flush=True)
                    time.sleep(1)
                continue

        elif r.status_code == 429:
            print(f"Ratelimit waiting {r.headers['Retry-After']} seconds...")
            limit = round(int(r.headers['Retry-After']) / 2)
            for i in range(limit, 0, -1):
                print(f"{i}", end="\r", flush=True)
                time.sleep(1)
            continue
        else:
            print(f"User {USER_ID} does not exists")
    conn.close()

def get_all_depop_items(data, baseurl, slugs, args, begin):
    # Start from slug args.start_from (-b)
    if args.start_from:
        for i in data['products']:
            # Prevent duplicates
            if not i['slug'] in slugs:
                if args.start_from == i['slug'] or begin == True:
                    begin = True
                    slugs.append(i['slug'])
    else:
        # start from 0
        for i in data['products']:
            # Prevent duplicates
            if not i['slug'] in slugs:
                slugs.append(i['slug'])
    while True:

        url = baseurl + f"&offset_id={data['meta']['last_offset_id']}"
        print(url)
        try:
            data = requests.get(url).json()
            # print(data)
        except:
            print(requests.get(url).text)
            exit()
            break
        # Start from slug args.start_from (-b)
        if args.start_from:
            for i in data['products']:
                # Prevent duplicates
                if not i['slug'] in slugs:
                    if args.start_from == i['slug'] or begin == True:
                        begin = True
                        slugs.append(i['slug'])
            if data['meta']['end'] == True:
                break
        else:
            # start from 0
            for i in data['products']:
                # Prevent duplicates
                if not i['slug'] in slugs:
                    slugs.append(i['slug'])
            if data['meta']['end'] == True:
                break
    return slugs

def download_depop_data(userids):
    Platform = "Depop"
    for userid in userids:
        userid = userid.strip()
        print(userid)
        slugs = []
        # Get userid from username
        url = f"https://webapi.depop.com/api/v1/shop/{userid}/"
        print(url)
        data = requests.get(url).json()

        id = str(data['id'])
        last_seen = str(data['last_seen'])
        bio = str(data['bio']).encode("UTF-8")
        followers = str(data['followers'])
        following = str(data['following'])
        try:
            initials = str(data['initials']).encode("UTF-8")
        except UnicodeEncodeError:
            initials = None
        items_sold = str(data['items_sold'])
        last_name = str(data['last_name']).encode("UTF-8")
        first_name = str(data['first_name']).encode("UTF-8")
        reviews_rating = str(data['reviews_rating'])
        reviews_total = str(data['reviews_total'])
        username = str(data['username'])
        verified = str(data['verified'])
        website = str(data['website'])
        filepath = None
        if len(data['picture']) > 0:
            photo = data['picture']['300'][:-6] + "U0.jpg"
            print(photo)
            try:
                os.mkdir(f"downloads/Avatars/")
            except OSError:
                print("Creation of the directory failed or the folder already exists ")
            req = requests.get(photo)
            filepath = f'downloads/Avatars/{username}_{id}.jpeg'
            if not os.path.isfile(filepath):
                with open(filepath, 'wb') as f:
                    f.write(req.content)
                print(f"Avatar saved to {filepath}")
        else:
            print('File already exists, skipped.')
        params = (username, id, bio, first_name, followers, following, initials, items_sold, last_name, last_seen, filepath, reviews_rating, reviews_total, verified,website)
        c.execute(
            "INSERT OR IGNORE INTO Depop_Users(Username, User_id, bio, first_name, followers, following, initials, items_sold, last_name, last_seen, Avatar, reviews_rating, reviews_total, verified, website) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            params)
        conn.commit()



        baseurl = f"https://webapi.depop.com/api/v1/shop/{id}/products/?limit=200"
        data = requests.get(baseurl).json()
        print("Fetching all produts...")
        begin = False
        slugs = get_all_depop_items(data, baseurl, slugs, args, begin)

        if args.sold_items:
            baseurl = f"https://webapi.depop.com/api/v1/shop/{id}/filteredProducts/sold?limit=200"
            data = requests.get(baseurl).json()
            get_all_depop_items(data, baseurl, slugs, args, begin)

        print("Got all products. Start Downloading...")
        print(len(slugs))
        
        depop_user_path = "downloads/" + str(userid) + '/'
        
        try:
            os.mkdir(depop_user_path)
        except OSError:
            print("Creation of the directory %s failed or the folder already exists " % depop_user_path)
        for slug in slugs:
            url = f"https://webapi.depop.com/api/v2/product/{slug}"
            print(slug)
            try:
                product_data = requests.get(url)
                if product_data.status_code == 200:
                    product_data = product_data.json()
                elif product_data.status_code == 429:
                    print(f"Ratelimit waiting 60 seconds...")
                    limit = 60
                    for i in range(limit, 0, -1):
                        print(f"{i}", end="\r", flush=True)
                        time.sleep(1)
                    continue
                elif product_data.status_code == 404:
                    print("Product not found")
                    continue
            except ValueError:
                print("Error decoding JSON data. Skipping...")
                continue

            product_id = product_data['id']
            try:
                Gender = product_data['gender']
            except KeyError:
                Gender = None
            try:
                Gender = product_data['gender']
            except KeyError:
                Gender = None
            try:
                Category = product_data['group']
            except KeyError:
                Category = product_data['categoryId']
            try:
                subcategory = product_data['productType']
            except KeyError:
                subcategory = None
            address = product_data['address']
            dateUpdated = product_data['dateUpdated']
            try:
                State = product_data['condition']['name']
            except KeyError:
                State = None

            Price = product_data['price']['priceAmount'] + product_data['price']['currencyName']
            description = product_data['description']
            Sold = product_data['status']
            title = slug.replace("-"," ")
            product_title = title.split(userid + " ", 1)[1]

            Colors = []
            # Get discountedPriceAmount if available
            try:
               discountedPriceAmount = product_data['price']['discountedPriceAmount']
            except KeyError:
                discountedPriceAmount = None
                pass
            # Get colors if available
            try:
                for color in product_data['colour']:
                    Colors.append(color['name'])
            except KeyError:
                pass

            # Get brand if available
            try:
                Brand = product_data['brandName']
            except:
                Brand = None
            sizes = []
            # Get size if available
            try:
                for size in product_data['sizes']:
                    sizes.append(size['name'])
            except KeyError:
                pass
            
            # Get condition if available
            try:
                Condition = product_data['condition']['name']
            except:
                Condition = None
            
            depop_product_path = depop_user_path + str(product_title) + ' (' + str(product_id) + ')/'
            try:
                os.mkdir(depop_product_path)
            except OSError:
                print ("Creation of the directory %s failed or the folder already exists " % depop_product_path)
            else:
                print ("Successfully created the directory %s " % depop_product_path)


            depop_product_file_path = depop_product_path + 'product_info.txt'
            with open(depop_product_file_path, 'w', encoding="UTF-8") as product_file:
                product_info = {
                    "id": product_id,
                    "title": product_title,
                    "description": description + '\n-----------',
                    "size": sizes,
                    "price": Price,
                    "status": product_data["status"],
                    "condition": Condition,
                    "product_gender": product_data["gender"],
                    "brand": Brand,
                    "product_group": Category,
                    "product_type": subcategory,
                    "updated": product_data["dateUpdated"]
                    }
                    
                for key, value in product_info.items(): 
                    product_file.write('%s: %s\n' % (key, value))

            for images in product_data['pictures']:
                
                for i in images:
                    full_size_url = i['url']
                    img_name = i['id']

                filepath = depop_product_path + str(img_name) + '.jpg'
                if not args.disable_file_download:
                    if not os.path.isfile(filepath):
                        c.execute(
                            f"SELECT ID FROM Depop_Data WHERE ID = {product_id}")
                        result = c.fetchone()
                        if result:
                            # Already exists
                            c.execute('''UPDATE Depop_Data SET Image = ? WHERE ID = ?''', (filepath, product_id))
                            conn.commit()
                            req = requests.get(full_size_url)
                            with open(filepath, 'wb') as f:
                                f.write(req.content)
                            print(f"Image saved to {filepath}")
                        else:
                            print(img_name)
                            print(full_size_url)
                            req = requests.get(full_size_url)
                            params = (
                            product_id, id, Sold, Gender, Category, subcategory, ','.join(sizes), State, Brand, ','.join(Colors), Price, filepath, description, title, Platform, address, discountedPriceAmount, dateUpdated)
                            c.execute(
                                "INSERT OR IGNORE INTO Depop_Data(ID, User_id, Sold, Gender, Category, subcategory, size, State, Brand, Colors, Price, Image, Description, Title, Platform, Address, discountedPriceAmount, dateUpdated)VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                params)
                            conn.commit()
                            with open(filepath, 'wb') as f:
                                f.write(req.content)
                            print(f"Image saved to {filepath}")
                    else:
                        print('File already exists, skipped.')
                elif args.disable_file_download:
                    c.execute(
                        f"SELECT ID FROM Depop_Data WHERE ID = {product_id}")
                    result = c.fetchone()
                    if result:
                        #Already exists
                        continue
                    else:
                        params = (
                            product_id, Sold, id, Gender, Category, subcategory, ','.join(sizes), State, Brand, ','.join(Colors),
                            Price, description, title, Platform, address, discountedPriceAmount, dateUpdated)
                        c.execute(
                            "INSERT OR IGNORE INTO Depop_Data(ID, Sold, User_id, Gender, Category, subcategory, size, State, Brand, Colors, Price, description, title, Platform, Address, discountedPriceAmount, dateUpdated)VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            params)
                        conn.commit()

            # Download videos
            if len(product_data['videos']) > 0:
                for x in product_data['videos']:
                    for source in x['sources']:
                        if source['format'] == 'MP4':
                            video_url = source['url']
                            file_name = video_url.split('/')[5]
                            filepath = 'downloads/' + str(userid) + '/' + str(file_name)
                            if not args.disable_file_download:
                                if not os.path.isfile(filepath):
                                    req = requests.get(video_url)
                                    print(video_url)
                                    params = (
                                        product_id, Sold, id, Gender, Category, subcategory, ','.join(sizes), State, Brand,
                                        ','.join(Colors), Price, filepath, description, title, Platform, address, discountedPriceAmount, dateUpdated)
                                    c.execute(
                                        "INSERT OR IGNORE INTO Depop_Data(ID, Sold, User_id, Gender, Category, subcategory, size, State, Brand, Colors, Price, Image, description, title, Platform, Address, discountedPriceAmount, dateUpdated)VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                        params)
                                    conn.commit()
                                    with open(filepath, 'wb') as f:
                                        f.write(req.content)
                                    print(f"Video saved to {filepath}")
                                else:
                                    if not args.disable_file_download:
                                        print('File already exists, skipped.')
                            elif args.disable_file_download:
                                c.execute(
                                    f"SELECT ID FROM Depop_Data WHERE ID = {product_id}")
                                result = c.fetchone()
                                if result:
                                    # Already exists
                                    continue
                                else:
                                    params = (
                                        product_id, Sold, id, Gender, Category, subcategory, ','.join(sizes), State,
                                        Brand, ','.join(Colors),
                                        Price, description, title, Platform, address, discountedPriceAmount, dateUpdated)
                                    c.execute(
                                        "INSERT OR IGNORE INTO Depop_Data(ID, Sold, User_id, Gender, Category, subcategory, size, State, Brand, Colors, Price, description, title, Platform, Address, discountedPriceAmount, dateUpdated)VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                        params)
                                    conn.commit()





#Import users from txt file
with open('users.txt', 'r', encoding='utf-8') as list_of_users:
            userids = list_of_users.readlines()

if args.Depop:
    download_depop_data(userids)
elif args.priv_msg:
    if args.user_id and args.session_id:
        user_id = args.user_id
        session_id = args.session_id
        download_priv_msg(session_id, user_id)
    else:
        print("Please use option -u and -s")
        exit()
else:
    session = vinted_session()
    download_vinted_data(userids, session)
