import time
import pickle
import requests

# We should probably insert these constants into the program
# via config file or environment variables once it's deployed.

USERNAME = ''
PASSWORD = ''
INSTANCE_URL = 'mander.xyz'
COMMUNITY_NAME = 'plantid'
API_KEY = ''
RETRY_TIME = 10
POLLING_POST_LIMIT = 5
POLLING_TIME = 60 


# --- Main loop ---


def main_loop():
    # Load list of already processed posts from processed.bin
    # (An empty file with this name needs to be created when the bot is being set up or it will not work)
    processed = load_processed('processed.bin')

    API_URL = f'https://{INSTANCE_URL}/api/v3'

    # If request error occurs, attempts to retry automatically
    while True:
        try:
            jwt = login(API_URL, USERNAME, PASSWORD)

            # Start polling lemmy for new posts
            while True:
                posts = get_posts(API_URL, jwt, POLLING_POST_LIMIT, 'New', COMMUNITY_NAME)

                for post in posts:
                    if (id := post['post']['id']) in processed:
                        continue

                    handle_post(API_URL, jwt, post)

                    processed.append(id)
                    dump_processed('processed.bin', processed)

                time.sleep(POLLING_TIME)

        except requests.RequestException:
            time.sleep(RETRY_TIME)
            continue


# --- Post handling ---


def handle_post(api_url, jwt, post):
    if (url := post['post']['url']) == None:
        return

    # Return if the url on the post is not an image
    if url.split('.')[-1] not in ['jpg', 'jpeg', 'png', 'webp']:
        return
    
    plant_id = requests.get(f'https://my-api.plantnet.org/v2/identify/all?api-key={API_KEY}', {
        'images': [url],
        'organs': ['auto']
    }).json()
    
    # If the API request fails, the response will contain a 'statusCode' attribute
    if 'statusCode' in plant_id:
        return

    table = ''
    for result in plant_id['results'][:5]:
        common_name = result['species']['commonNames'][0] if len(result['species']['commonNames']) != 0 else '/'
        scientific_name = result['species']['scientificNameWithoutAuthor']
        score = format(result['score'] * 100, '.2f')

        table += f'|{common_name}|{scientific_name}|{score} %|\n'

    comment_text = f'''
**Automatic identification via PlantNet summary**

Most likely match: **{plant_id['bestMatch']}**

|Common name|Scientific name|Likeliness|
|-|-|-|
{table}
Beep, boop

I'm a bot, and this action was performed automatically.
'''

    comment(api_url, jwt, comment_text, post['post']['id'])


# --- Lemmy API operations ---


def login(api_url, username_or_email, password):
    res = requests.post(f'{api_url}/user/login', json={
        'username_or_email': username_or_email,
        'password': password,
    })

    return res.json()['jwt']


def get_posts(api_url, auth, limit, sort, community_name):
    res = requests.get(f'{api_url}/post/list', params={
        'auth': auth,
        'limit': limit,
        'sort': sort,
        'community_name': community_name,
    })

    return res.json()['posts']


def comment(api_url, auth, content, post_id):
    requests.post(f'{api_url}/comment', json={
        'auth': auth,
        'content': content,
        'post_id': post_id
    })


# --- Other utility functions ---


def load_processed(path):
    with open(path, 'rb') as f: 
        data = f.read()

        if data == b'':
            return []
        
        return pickle.loads(data)


def dump_processed(path, processed):
    with open(path, 'wb') as f:
        f.write(pickle.dumps(processed))


if __name__ == '__main__':
    main_loop()