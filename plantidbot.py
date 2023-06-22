import asyncio
import websockets
import json
import time
import pickle
import requests

# We should probably insert these constants into the program
# via config file or environment variables once it's deployed.

USERNAME = ''
PASSWORD = ''
INSTANCE_URL = ''
COMMUNITY_ID = 0 # This needs to be set to the ID of !plantid@mander.xyz (or wherever we want it to operate)
API_KEY = ''


# --- Main loop ---


async def main_loop():
    # Load list of already processed posts from processed.bin
    # (An empty file with this name needs to be created when the bot is being set up or it will not work)
    processed = load_processed('processed.bin')

    # If connection fails, attempts to reconnect automatically in 10s
    async for s in websockets.connect(f'wss://{INSTANCE_URL}/api/v3/ws'):
        try:
            jwt = await login(s, USERNAME, PASSWORD)

            # Tells Lemmy API to start sending us updates for new posts
            await join(s, COMMUNITY_ID)

            while True:
                update = json.loads(await s.recv())

                if update['op'] != 'CreatePost':
                    continue

                if (id := update['data']['post_view']['post']['id']) in processed:
                    continue

                await handle_post(s, update, jwt)

                processed.append(id)
                dump_processed('processed.bin', processed)

        except websockets.ConnectionClosedError:
            time.sleep(10)
            continue


# --- Post handling ---


async def handle_post(s, post, jwt):
    if (url := post['data']['post_view']['post']['url']) == None:
        return

    # Return if the url on the post is not a Lemmy-hosted image
    if 'pictrs' not in url:
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
        score = result['score']

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

    # comment(s, jwt, post['data']['post_view']['post']['id'], comment_text)
    print(comment_text)


# --- Lemmy API operations ---


async def login(s, username, password):
    await s.send(json.dumps({
        'op': 'Login',
        'data': {
            'username_or_email': username,
            'password': password
        }
    }))

    return json.loads(await s.recv())['data']['jwt']


async def join(s, community_id):
    await s.send(json.dumps({
        'op': 'CommunityJoin',
        'data': {
            'community_id': community_id
        }
    }))

    return json.loads(await s.recv())


async def comment(s, jwt, post_id, text):
    await s.send(json.dumps({
        'op': 'CreateComment',
        'data': {
            'content': text,
            'parent_id': None,
            'post_id': post_id,
            'form_id': None,
            'auth': jwt
        }
    }))

    return json.loads(await s.recv())


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


asyncio.run(main_loop())