from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import string
import random


app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

# Global dict to store quiz codes and their corresponding room IDs
active_quizzes = {}

CREDENTIALS_FILE = 'Data/credentials.json'


def read_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        return {}
    try:
        with open(CREDENTIALS_FILE) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def write_credentials(username, password):
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    credentials = read_credentials()
    hashed_password = generate_password_hash(password)
    credentials[username] = hashed_password
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        credentials = read_credentials()

        # Check if the username already exists
        if username in credentials:
            # If yes, return to the registration page with a message
            message = f"It looks like there is already a QUIZZZ account with the username {username}, log into the account <a href='/login'>here</a>."
            return render_template('register.html', message=message)
        else:
            # If no, proceed with registration
            write_credentials(username, password)
            flash('Registration successful. Please login.')
            return redirect(url_for('login'))
    else:
        # GET request, just show the registration form
        return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        credentials = read_credentials()
        if username in credentials and check_password_hash(credentials[username], password):
            session['username'] = username
            return redirect(url_for('instructor_dashboard'))
        else:
            flash('Invalid credentials. Please try again.')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
def home():
    return redirect(url_for('register'))


@app.route('/instructor_dashboard')
def instructor_dashboard():
    return render_template('instructor_dashboard.html')


@app.route('/start_quiz', methods=['GET'])
def start_quiz():
    username = session.get('username')
    if not username:
        flash('Please log in to access your quizzes.')
        return redirect(url_for('login'))

    quizzes_file_path = os.path.join('Data', f'{username}_quizzes.json')
    if os.path.exists(quizzes_file_path):
        with open(quizzes_file_path) as file:
            quizzes = json.load(file)
    else:
        quizzes = []

    return render_template('start_quiz.html', quizzes=quizzes)


def generate_unique_code():
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
    return code


@app.route('/pregame_lobby/<quiz_title>', methods=['GET'])
def pregame_lobby(quiz_title):
    # Optional: You may want to pass quiz details to the pregame lobby page
    return render_template('pregame_lobby.html', quiz_title=quiz_title)


@app.route('/create_quiz', methods=['GET', 'POST'])
def create_quiz():
    print("Form Data Received:", request.form)  # Print all form data received
    if request.method == 'POST':
        username = session.get('username')
        if not username:
            print("No username in session.")  # Debug: Check if username is missing
            return redirect(url_for('login'))

        quiz_data = {
            "title": request.form['title'],
            "questions": []
        }

        # Calculate number of questions based on the number of prompts received
        num_questions = len([key for key in request.form.keys() if key.startswith('questions[prompt]')])

        print(f"Number of questions submitted: {num_questions}")  # Debug: Check the number of questions

        for i in range(num_questions):
            prompt = request.form.get(f'questions[prompt][{i}]')
            question_type = request.form.get(f'questions[type][{i}]')
            print(f"Processing Question {i+1}: Type={question_type}, Prompt={prompt}")  # Debug: Print each question's type and prompt

            question = {"prompt": prompt, "type": question_type}

            if question_type == "multiple choice":
                options = request.form.get(f'questions[options][{i}]').split(',')
                correct_answer = request.form.get(f'questions[correct_answer][{i}]')
                question["options"] = options
                question["correct_answer"] = correct_answer
                print(f"Multiple Choice Options: {options}, Correct Answer: {correct_answer}")  # Debug

            elif question_type == "true/false":
                correct_answer = request.form.get(f'questions[correct_answer][{i}]')
                question["correct_answer"] = correct_answer
                print(f"True/False Correct Answer: {correct_answer}")  # Debug

            elif question_type == "drag and drop":
                items = request.form.get(f'questions[items][{i}]').split(',')
                correct_order = request.form.get(f'questions[correct_order][{i}]').split(',')
                question["items"] = items
                question["correct_order"] = [int(index) - 1 for index in correct_order]  # Assuming 1-based index, adjust if necessary
                print(f"Drag and Drop Items: {items}, Correct Order: {correct_order}")  # Debug

            quiz_data['questions'].append(question)

        quizzes_file_path = os.path.join('Data', f'{username}_quizzes.json')
        quizzes = []
        try:
            if os.path.exists(quizzes_file_path):
                with open(quizzes_file_path, 'r') as file:
                    quizzes = json.load(file)
        except json.JSONDecodeError:
            quizzes = []

        quizzes.append(quiz_data)
        print(f"Saving Quiz Data: {quiz_data}")  # Debug: Confirm quiz data before saving
        with open(quizzes_file_path, 'w') as file:
            json.dump(quizzes, file, indent=4)

        return redirect(url_for('instructor_dashboard'))

    return render_template('create_quiz.html')


@app.route('/quiz_manager', methods=['GET', 'POST'])
def quiz_manager():
    username = session.get('username')
    if not username:
        flash('Please log in to access this page.')
        return redirect(url_for('login'))

    quizzes_file_path = os.path.join('Data', f'{username}_quizzes.json')
    quizzes = []
    if os.path.exists(quizzes_file_path):
        with open(quizzes_file_path) as file:
            quizzes = json.load(file)

    selected_quiz = request.args.get('quiz_title')
    quiz_data = None
    if selected_quiz:
        quiz_data = next((quiz for quiz in quizzes if quiz['title'] == selected_quiz), None)

    if request.method == 'POST':
        title = request.form['title']
        questions = []
        num_questions = len([key for key in request.form.keys() if key.startswith('questions[prompt]')])
        for i in range(num_questions):
            question = {
                "prompt": request.form.get(f'questions[prompt][{i}]'),
                "type": request.form.get(f'questions[type][{i}]'),
                "options": request.form.get(f'questions[options][{i}]', '').split(','),
                "correct_answer": request.form.get(f'questions[correct_answer][{i}]')
            }
            questions.append(question)

        # Update or add new quiz
        if quiz_data:
            quizzes = [quiz for quiz in quizzes if quiz['title'] != title]  # Remove old version if title changed
        else:
            quiz_data = {}

        quiz_data['title'] = title
        quiz_data['questions'] = questions
        quizzes.append(quiz_data)

        with open(quizzes_file_path, 'w') as file:
            json.dump(quizzes, file, indent=4)

        flash('Quiz saved successfully.')
        return redirect(url_for('instructor_dashboard'))

    return render_template('quiz_manager.html', quizzes=quizzes, quiz_data=quiz_data)


@app.route('/modify_quiz', methods=['GET'])
def modify_quiz():
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))

    quizzes_file_path = os.path.join('Data', f'{username}_quizzes.json')
    if os.path.exists(quizzes_file_path):
        with open(quizzes_file_path, 'r') as file:
            quizzes = json.load(file)
    else:
        quizzes = []

    # Pass the quizzes to the template
    return render_template('modify_quiz.html', quizzes=quizzes)


@app.route('/edit_quiz/<path:quiz_title>', methods=['GET', 'POST'])
def edit_quiz(quiz_title):
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))

    quizzes_file_path = os.path.join('Data', f'{username}_quizzes.json')
    quizzes = []
    if os.path.exists(quizzes_file_path):
        with open(quizzes_file_path, 'r') as file:
            quizzes = json.load(file)
    quiz = next((q for q in quizzes if q['title'] == quiz_title), None)

    if not quiz:
        flash('Quiz not found.')
        return redirect(url_for('modify_quiz'))

    if request.method == 'POST':
        # Update quiz title
        quiz['title'] = request.form['title']

        # Process questions
        new_questions = []
        for i in range(len(request.form.getlist('questions[prompt]'))):
            if not request.form.get(f'delete_question_{i}', False):
                question = {
                    "prompt": request.form.get(f'questions[prompt][{i}]'),
                    # Add other question details here, similar to how questions are processed in create_quiz
                }
                new_questions.append(question)
        quiz['questions'] = new_questions

        # Save the updated quiz list back to the file
        with open(quizzes_file_path, 'w') as file:
            json.dump(quizzes, file, indent=4)

        flash('Quiz updated successfully.')
        return redirect(url_for('instructor_dashboard'))

    return render_template('edit_quiz.html', quiz=quiz, quiz_title=quiz_title)


@app.route('/previous_results')
def previous_results():
    return "Placeholder for viewing previous results."


# Student (phone) side

# Global dictionary to store active quiz codes
active_quiz_codes = {}


def generate_unique_code():
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
    return code


@app.route('/join_quiz', methods=['GET', 'POST'])
def join_quiz():
    if request.method == 'POST':
        code = request.form['code'].upper()
        if code in active_quiz_codes:
            quiz_id = active_quiz_codes[code]
            # Redirect to the quiz page, or handle joining the quiz by its ID
            return redirect(url_for('quiz_page', quiz_id=quiz_id))
        else:
            flash('Invalid code. Please try again.')
            return redirect(url_for('join_quiz'))
    return render_template('join_quiz.html')


@app.route('/quiz/<code>')
def quiz(code):
    return render_template('quiz.html', code=code)


@socketio.on('join_quiz')
def on_join(data):
    room = data['code']
    join_room(room)
    emit('status', {'msg': f'{request.sid} has joined the quiz.'}, room=room)


@socketio.on('submit_answer')
def on_answer(data):
    room = session.get('quiz_id')
    # Process answer here and emit results or feedback
    emit('feedback', {'msg': 'Your answer has been received.'}, room=room)


@socketio.on('join_quiz')
def handle_join_quiz(data):
    quiz_code = data['quiz_code']
    # Join the quiz room
    join_room(quiz_code)
    emit('status', {'msg': f'Joined quiz {quiz_code}'}, to=quiz_code)


@socketio.on('submit_answer')
def handle_submit_answer(data):
    # Process submitted answer
    pass


if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)

