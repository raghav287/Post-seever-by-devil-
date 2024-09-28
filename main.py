from flask import Flask, render_template, request, redirect, flash, session
import os
import requests
import re
import time
from pymongo import MongoClient
import uuid
import threading

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MongoDB setup
client = MongoClient('mongodb+srv://kareem001ar:4oAhjHm7yUG0z4S2@cluster0.fnsuw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['tasks_database']
tasks_collection = db['tasks']

# Task Thread Pool
task_threads = {}

# Database functions using MongoDB
def add_task(task_id, convo_id, comment_name, delay, comments, cookies, username):
    task = {
        'id': task_id,
        'convo_id': convo_id,
        'comment_name': comment_name,
        'delay': delay,
        'comments': comments,
        'cookies': cookies,
        'username': username
    }
    tasks_collection.insert_one(task)

def get_tasks(username):
    tasks = list(tasks_collection.find({'username': username}, {'_id': 0}))
    return tasks

def remove_task(task_id):
    tasks_collection.delete_one({'id': task_id})

def get_all_tasks():
    tasks = list(tasks_collection.find({}, {'_id': 0}))
    return tasks

# Initialize tasks from the database on startup
def autostart_tasks():
    tasks = get_all_tasks()
    for task in tasks:
        start_task_thread(task['id'], task['convo_id'], task['comment_name'], task['delay'], task['comments'], task['cookies'], task['username'])

def start_task_thread(task_id, convo_id, comment_name, delay, comments, cookies, username):
    def task_worker():
        devil(convo_id, comment_name, delay, cookies, comments, username, task_id)

    task_thread = threading.Thread(target=task_worker)
    task_threads[task_id] = task_thread
    task_thread.start()

def make_request(url, headers, cookie):
    try:
        response = requests.get(url, headers=headers, cookies={'Cookie': cookie})
        return response.text
    except requests.exceptions.RequestException:
        return None

def devil(convo_id, comment_name, delay, cookies_data, comments, username, task_id):
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 11; RMX2144 Build/RKQ1.201217.002; wv) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/103.0.5060.71 '
            'Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/375.1.0.28.111;]'
        )
    }

    valid_cookies = []

    for cookie in cookies_data:
        response = make_request('https://business.facebook.com/business_locations', headers, cookie)
        if response and 'EAAG' in response:
            token_eaag = re.search(r'(EAAG\w+)', response)
            if token_eaag:
                valid_cookies.append((cookie, token_eaag.group(1)))

    if not valid_cookies:
        return '[!] No valid cookie found. Exiting...'

    x, cookie_index = 0, 0

    while x < len(comments) and task_id in task_threads:
        try:
            time.sleep(delay)
            comment = comments[x].strip()
            comment_with_name = f'{comment_name}: {comment}'
            current_cookie, token_eaag = valid_cookies[cookie_index]

            data = {'message': comment_with_name, 'access_token': token_eaag}
            response2 = requests.post(
                f'https://graph.facebook.com/{convo_id}/comments/', 
                data=data, 
                cookies={'Cookie': current_cookie}
            ).json()

            if 'id' in response2:
                x += 1
                cookie_index = (cookie_index + 1) % len(valid_cookies)
            else:
                x += 1
                cookie_index = (cookie_index + 1) % len(valid_cookies)

        except requests.exceptions.RequestException:
            time.sleep(5.5)
        except Exception as e:
            return f'[!] An unexpected error occurred: {e}'

    if task_id in task_threads:
        del task_threads[task_id]

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' not in session:
        return redirect('/login')

    if request.method == 'POST':
        convo_id = request.form.get('convo_id')
        comment_name = request.form.get('comment_name')
        delay = int(request.form.get('delay'))

        cookies_file = request.files['cookies_file']
        comments_file = request.files['comments_file']

        cookies = read_file(cookies_file)
        comments = read_file(comments_file)

        if not convo_id or not comment_name or not cookies or not comments:
            flash('Please fill all fields and ensure files are properly uploaded!')
            return redirect('/')

        task_id = str(uuid.uuid4())
        add_task(task_id, convo_id, comment_name, delay, comments, cookies, session['username'])
        start_task_thread(task_id, convo_id, comment_name, delay, comments, cookies, session['username'])

        flash(f'Task started with Convo ID: {convo_id}')
        return redirect('/')

    tasks = get_tasks(session['username'])
    return render_template('index.html', tasks=tasks)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Please enter both username and password!')
            return redirect('/login')

        response = requests.get('https://pastebin.com/raw/pCJAvbWJ')
        credentials = response.text.splitlines()

        if f'{username}:{password}' in credentials:
            session['username'] = username
            return redirect('/')
        else:
            flash('Invalid username or password!')
            return redirect('/login')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/login')

@app.route('/stop_task/<task_id>')
def stop_task(task_id):
    if task_id in task_threads:
        del task_threads[task_id]
        remove_task(task_id)
        flash(f'Task {task_id} has been stopped and removed.')
    else:
        flash(f'Task {task_id} not found or already stopped.')
    return redirect('/')

def read_file(file):
    try:
        return file.read().decode('utf-8').splitlines()
    except Exception as e:
        return None

if __name__ == '__main__':
    autostart_tasks()  # Auto-start tasks on startup
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
