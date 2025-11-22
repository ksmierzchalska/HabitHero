from typing import Optional
from flask import Flask, flash, redirect, render_template, request, session, url_for
import pyodbc
from flask_wtf import FlaskForm 
from wtforms import EmailField, StringField, PasswordField, SubmitField, IntegerField, SelectField, BooleanField, HiddenField
from wtforms.validators import InputRequired, Email, EqualTo, Length, DataRequired, NumberRange, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from datetime import datetime, timedelta
import random


# KONFIGURACJA BAZY DANYCH


connection = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=Kasia;'
    'DATABASE=HabitHero;'
    'Trusted_Connection=yes;'
    'TrustServerCertificate=yes'
)

cursor = connection.cursor()

# Test połączenia do bazy
try:
    cursor.execute('SELECT name FROM sys.tables')
    tables = cursor.fetchall()
    print('Połączenie dziala! Tabele:', tables)
except Exception as e:
    print('Błąd połączenia', e)

# KONFIGURACJA APLIKACJI FLASK


app = Flask(__name__)
app.secret_key = "my_secret_key"
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# MODELE

class User(UserMixin):
    def __init__(self, id, email, handle, is_admin):
        self.id = id
        self.email = email
        self.handle = handle 
        self.is_admin = is_admin


# FORMULARZE

class RegistrationForm(FlaskForm):
    firstname = StringField('Imię', validators=[InputRequired(message='To pole jest wymagane')])
    lastname = StringField('Nazwisko', validators=[InputRequired(message='To pole jest wymagane')])
    email = EmailField('Email', validators=[InputRequired(message='To pole jest wymagane'), Email(message='Wprowadź poprawny adres email')])
    handle = StringField('Wyświetlana nazwwa', validators=[InputRequired(message='To pole jest wymagane')])
    password = PasswordField('Hasło', validators=[InputRequired(message='To pole jest wymagane'),Length(min=6, message='Hasło musi mieć co najmniej 6 znaków')])
    password_check = PasswordField('Powtórz hasło', validators=[InputRequired(message='To pole jest wymagane'), EqualTo('password', message='Hasła nie są takie same')])
    submit = SubmitField('Zarejestruj się')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(message='To pole jest wymagane'), Email(message='Wprowadź poprawny adres email')])
    password = PasswordField('Hasło', validators=[DataRequired(message='To pole jest wymagane')])
    submit = SubmitField('Zaloguj się')

class SectionForm(FlaskForm):
    name = StringField("Nazwa sekcji", validators=[InputRequired()])
    submit = SubmitField("Dodaj sekcję")

class ChallengeForm(FlaskForm):
    name = StringField("Nazwa wyzwania", validators=[InputRequired()])
    section_id = SelectField("Sekcja", coerce=int, validators=[InputRequired()])
    duration_days = IntegerField("Czas trwania:", validators=[InputRequired(), NumberRange(min=1)])
    level = SelectField("Poziom", choices=[("niski","niski"),("średni","średni"),("wysoki","wysoki")])
    xp = IntegerField("XP do zdobycia", validators=[InputRequired(), NumberRange(min=0)])
    is_active = BooleanField("Czy aktywne?", default=True)
    submit = SubmitField('Dodaj wyzwanie')

class MainGoalForm(FlaskForm):
    name = StringField("Nazwa celu:", validators=[InputRequired()])
    duration_days = IntegerField("Przewidywany czas trwania (dni):", validators=[InputRequired(), NumberRange(min=1)])
    submit = SubmitField("Dodaj cel")

class EditGoalForm(FlaskForm):
    goal_id = HiddenField("Goal ID", validators=[InputRequired()])
    name = StringField("Nazwa celu:", validators=[InputRequired()])
    duration_days = IntegerField("Przewidywany czas trwania (dni):", validators=[InputRequired(), NumberRange(min=1)])
    submit = SubmitField("Zapisz zmiany")

class HabitForm(FlaskForm):
    name = StringField("Nazwa nawyku", validators=[InputRequired()])
    description = StringField("Opis (opcjonalnie)")
    target_value = IntegerField("Cel dzienny", validators=[InputRequired(), NumberRange(min=1)])
    unit = StringField("Jednostka (np. szklanki, minuty, km)")
    category = SelectField("Kategoria", choices=[
        ('health', 'Zdrowie'),
        ('fitness', 'Fitness'), 
        ('nutrition', 'Odżywianie'),
        ('mental', 'Zdrowie psychiczne'),
        ('productivity', 'Produktywność')
    ])
    color = StringField("Kolor")
    submit = SubmitField("Dodaj nawyk")

class HabitProgressForm(FlaskForm):
    value_achieved = IntegerField("Ilość wykonana", validators=[InputRequired(), NumberRange(min=0)])
    submit = SubmitField("Zapisz progres")

class UserSettingsForm(FlaskForm):
    daily_inspirations = BooleanField("Codzienne inspiracje motywacyjne")
    show_notifications = BooleanField("Pokazuj powiadomienia")
    handle = StringField("Nazwa użytkownika", validators=[InputRequired()])
    new_password = PasswordField("Nowe hasło (opcjonalnie)", validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField("Potwierdź nowe hasło", validators=[EqualTo('new_password', message='Hasła muszą się zgadzać')])
    submit = SubmitField("Zapisz zmiany")

# FUNKCJE POMOCNICZE

def add_points_to_user(user_id, amount, source='general'):
    """
    source: 'challenge' - punkty do rankingu
            'goal' - punkty prywatne  
            'habit' - punkty prywatne
            'general' - domyślne
    """
    try:
        cursor.execute("""
            SELECT LEVEL_POINTS, LEVEL_THRESHOLD, CURRENT_LEVEL, TOTAL_POINTS, RANKING_POINTS
            FROM USERS WHERE ID = ?
        """, (user_id,))
        data = cursor.fetchone()

        level_points = data[0]
        threshold = data[1]
        level = data[2]
        total_points = data[3]
        ranking_points = data[4] or 0

        # dodaj zdobyte punkty
        level_points += amount
        total_points += amount
        
        # jeśli punkty z wyzwania, dodaj do rankingu
        if source == 'challenge':
            ranking_points += amount

        badges_earned = []

        # sprawdź czy należy podnieść poziom (TYLKO na podstawie level_points)
        while level_points >= threshold and threshold <= 3000:
            level_points -= threshold
            level += 1
            threshold += 250

            # przyznanie odznaki jeśli jest przypisana
            cursor.execute("SELECT ID, NAME, DESCRIPTION FROM BADGES WHERE REQUIRED_POINTS = ?", (threshold,))
            badge = cursor.fetchone()
            if badge:
                cursor.execute("INSERT INTO USER_BADGES (USER_ID, BADGE_ID) VALUES (?, ?)", (user_id, badge[0]))
                badges_earned.append({
                    "id": badge[0],
                    "name": badge[1],
                    "description": badge[2]
                })

        cursor.execute("""
            UPDATE USERS
            SET LEVEL_POINTS=?, LEVEL_THRESHOLD=?, CURRENT_LEVEL=?, TOTAL_POINTS=?, RANKING_POINTS=?
            WHERE ID=?
        """, (level_points, threshold, level, total_points, ranking_points, user_id))
        connection.commit()

        if badges_earned:
            session['new_badges'] = badges_earned
            session['show_badge_notification'] = True

    except Exception as e:
        connection.rollback()
        print("Błąd:", e)

def remove_points_from_user(user_id, amount, source='general'):
    """
    Odejmuje punkty od użytkownika
    source: 'habit' - punkty prywatne
    """
    try:
        cursor.execute("""
            SELECT LEVEL_POINTS, LEVEL_THRESHOLD, CURRENT_LEVEL, TOTAL_POINTS, RANKING_POINTS
            FROM USERS WHERE ID = ?
        """, (user_id,))
        data = cursor.fetchone()

        level_points = data[0]
        threshold = data[1]
        level = data[2]
        total_points = data[3]
        ranking_points = data[4] or 0

        # odejmij punkty (nie mniej niż 0)
        level_points = max(0, level_points - amount)
        total_points = max(0, total_points - amount)

        cursor.execute("""
            UPDATE USERS
            SET LEVEL_POINTS=?, LEVEL_THRESHOLD=?, CURRENT_LEVEL=?, TOTAL_POINTS=?, RANKING_POINTS=?
            WHERE ID=?
        """, (level_points, threshold, level, total_points, ranking_points, user_id))
        connection.commit()


    except Exception as e:
        connection.rollback()
        print(f"Błąd przy odejmowaniu punktów: {e}")

def get_user_badges(user_id):
    """Pobiera odznaki zdobyte przez użytkownika"""
    try:
        cursor.execute("""
            SELECT B.ID, B.NAME, B.DESCRIPTION, B.CATEGORY, UB.EARNED_AT
            FROM USER_BADGES UB
            JOIN BADGES B ON UB.BADGE_ID = B.ID
            WHERE UB.USER_ID = ?
            ORDER BY UB.EARNED_AT DESC
        """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Błąd przy pobieraniu odznak: {e}")
        return []

def get_all_badges():
    """Pobiera wszystkie dostępne odznaki"""
    try:
        cursor.execute("SELECT ID, NAME, DESCRIPTION, REQUIRED_POINTS, CATEGORY FROM BADGES ORDER BY REQUIRED_POINTS")
        return cursor.fetchall()
    except Exception as e:
        print(f"Błąd przy pobieraniu wszystkich odznak: {e}")
        return []

def get_completed_goals(user_id):
    """Pobiera ukończone główne cele"""
    try:
        cursor.execute("""
            SELECT ID, NAME, DURATION_DAYS, CREATED, END_DATE
            FROM MAINGOALS 
            WHERE USER_ID = ? AND IS_ACTIVE = 0
            ORDER BY END_DATE DESC
        """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Błąd przy pobieraniu ukończonych celów: {e}")
        return []

def get_completed_challenges(user_id):
    """Pobiera ukończone wyzwania"""
    try:
        cursor.execute("""
            SELECT C.ID, C.NAME, S.NAME as SECTION_NAME, C.DURATION_DAYS, 
                   C.LEVEL, C.XP, UC.JoinedAt, UC.CompletedAt
            FROM CHALLENGES C
            JOIN SECTION S ON C.SECTION_ID = S.ID
            JOIN USERCHALLENGES UC ON C.ID = UC.CHALLENGEID
            WHERE UC.USERID = ? AND UC.CompletedAt IS NOT NULL
            ORDER BY UC.CompletedAt DESC
        """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Błąd przy pobieraniu ukończonych wyzwań: {e}")
        return []

def get_top_users(limit=10):
    """Pobiera top użytkowników według RANKING_POINTS (tylko z wyzwań)"""
    try:
        cursor.execute("""
            SELECT TOP (?) HANDLE, RANKING_POINTS, CURRENT_LEVEL
            FROM USERS 
            WHERE RANKING_POINTS > 0  -- Tylko użytkownicy z punktami z wyzwań
            ORDER BY RANKING_POINTS DESC
        """, (limit,))
        result = cursor.fetchall()
        return result
    except Exception as e:
        print(f"Błąd przy pobieraniu rankingu: {e}")
        return []

def get_user_settings(user_id):
    """Pobiera ustawienia użytkownika"""
    try:
        cursor.execute("""
            SELECT DAILY_INSPIRATIONS, SHOW_NOTIFICATIONS, HANDLE 
            FROM USERS WHERE ID = ?
        """, (user_id,))
        result = cursor.fetchone()
        print(f" DEBUG get_user_settings: user_id={user_id}, result={result}")
        return result
    except Exception as e:
        print(f"Błąd przy pobieraniu ustawień: {e}")
        return None

def get_daily_inspiration():
    """Zwraca losową inspirację motywacyjną z bazy danych"""
    try:
        cursor.execute("SELECT MESSAGE FROM DAILY_INSPIRATIONS ORDER BY NEWID()")
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            # Fallback jeśli baza jest pusta
            return "💫 Każdy dzień to nowa szansa na lepszą wersję siebie!"
    except Exception as e:
        
        return "🔥 Małe kroki prowadzą do wielkich celów - jesteś na dobrej drodze!"

# =============================================================================
# FUNKCJE DLA NAWYKÓW
# =============================================================================

def get_user_habits(user_id):
    """Pobiera tylko AKTYWNE nawyki użytkownika"""
    try:
        cursor.execute("""
            SELECT ID, NAME, DESCRIPTION, TARGET_VALUE, CURRENT_VALUE, UNIT, 
                   CATEGORY, COLOR, STREAK_DAYS, BEST_STREAK, IS_ACTIVE
            FROM HABITS 
            WHERE USER_ID = ? AND IS_ACTIVE = 1  -- TYLKO AKTYWNE
            ORDER BY CREATED_DATE DESC
        """, (user_id,))
        result = cursor.fetchall()
        return result
    except Exception as e:
        print(f"Błąd przy pobieraniu nawyków: {e}")
        return []

def update_habit_progress(habit_id, value_achieved):
    """Aktualizuje progres nawyku i zarządza streak'ami"""
    try:
        today = datetime.now().date()
        
        # Sprawdź czy potrzebny reset (nowy dzień)
        cursor.execute("SELECT LAST_RESET_DATE FROM HABITS WHERE ID = ?", (habit_id,))
        last_reset = cursor.fetchone()
        
        if last_reset and (last_reset[0] is None or last_reset[0] < today):
            # Resetuj przed dodaniem nowej wartości
            cursor.execute("UPDATE HABITS SET CURRENT_VALUE = 0, LAST_RESET_DATE = ? WHERE ID = ?", 
                         (today, habit_id))
        
        # Pobierz aktualne dane nawyku
        cursor.execute("""
            SELECT CURRENT_VALUE, TARGET_VALUE, STREAK_DAYS, BEST_STREAK, USER_ID, IS_ACTIVE
            FROM HABITS WHERE ID = ?
        """, (habit_id,))
        habit = cursor.fetchone()
        
        if not habit or not habit[5]:
            return False
            
        user_id = habit[4]
        target_value = habit[1]
        current_streak = habit[2]  # Aktualna passa TEGO NAWYKU
        best_streak = habit[3]
        
        # ZAWSZE ustaw wartość na tę wpisaną przez użytkownika
        new_value = value_achieved
        
        # Sprawdź czy cel został osiągnięty
        if new_value >= target_value:
            new_streak = current_streak + 1
            best_streak = max(best_streak, new_streak)
            add_points_to_user(user_id, 10, source='habit')
            
            #  Sprawdź odznaki za passę TEGO NAWYKU
            check_streak_badges(user_id, new_streak) 
            
        else:
            new_streak = 0
            best_streak = best_streak
        
        # Aktualizuj nawyk
        cursor.execute("""
            UPDATE HABITS 
            SET CURRENT_VALUE = ?, STREAK_DAYS = ?, BEST_STREAK = ?, 
                UPDATED_DATE = ?, LAST_RESET_DATE = ?
            WHERE ID = ?
        """, (new_value, new_streak, best_streak, datetime.now(), today, habit_id))
        
        # Zapisz w historii
        cursor.execute("""
            INSERT INTO HABIT_LOGS (HABIT_ID, VALUE_ACHIEVED, TARGET_VALUE, LOG_DATE)
            VALUES (?, ?, ?, ?)
        """, (habit_id, new_value, target_value, today))
        
        connection.commit()
        return True
        
    except Exception as e:
        connection.rollback()
        print(f"Błąd przy aktualizacji progresu: {e}")
        return False

def check_streak_badges(user_id, current_streak):
    """Sprawdza i przyznaje odznaki za aktualną passę - TYLKO gdy passa DOKŁADNIE osiągnie wymagany próg"""
    try:
        # Tylko określone progi
        required_thresholds = [7, 14, 30, 60, 90]
        
        # Sprawdź TYLKO czy aktualna passa odpowiada JEDNEMU z progów
        if current_streak not in required_thresholds:
            return []
        
        # Znajdź odznakę dla tego KONKRETNEGO progu
        cursor.execute("""
            SELECT ID, NAME, DESCRIPTION, REQUIRED_POINTS 
            FROM BADGES 
            WHERE CATEGORY = 'streak' AND REQUIRED_POINTS = ?
        """, (current_streak,))
        
        badge = cursor.fetchone()
        
        if not badge:
            return []
            
        badge_id, badge_name, badge_description, required_days = badge
        
        # Sprawdź czy użytkownik już ma tę KONKRETNĄ odznakę
        cursor.execute("""
            SELECT 1 FROM USER_BADGES 
            WHERE USER_ID = ? AND BADGE_ID = ?
        """, (user_id, badge_id))
        
        if cursor.fetchone():
            return []
        
        # Przyznaj TYLKO TĘ JEDNĄ odznakę
        cursor.execute("""
            INSERT INTO USER_BADGES (USER_ID, BADGE_ID, EARNED_AT)
            VALUES (?, ?, ?)
        """, (user_id, badge_id, datetime.now()))
        
        awarded_badges = [{
            'id': badge_id,
            'name': badge_name,
            'description': badge_description,
            'days': required_days
        }]
        
        connection.commit()
        
        # Zapisujemy w sesji żeby pokazać powiadomienie
        session['new_badges'] = awarded_badges
        session['show_badge_notification'] = True
        
        return awarded_badges
        
    except Exception as e:
        connection.rollback()
        print(f"Błąd przy sprawdzaniu odznak za passy: {e}")
        return []

def get_habit_stats(user_id, days=30):
    """Pobiera statystyki nawyków - TYLKO AKTYWNE"""
    try:
        # Najpierw sprawdźmy ile jest aktywnych nawyków
        cursor.execute("SELECT COUNT(*) FROM HABITS WHERE USER_ID = ? AND IS_ACTIVE = 1", (user_id,))
        active_count = cursor.fetchone()[0]
        print(f" Aktywnych nawyków: {active_count}")
        
        # Pobierz statystyki
        cursor.execute("""
            SELECT 
                H.NAME, 
                COUNT(DISTINCT CAST(HL.LOG_DATE AS DATE)) as completed_days,
                AVG(CAST(HL.VALUE_ACHIEVED as FLOAT)) as avg_value,
                H.STREAK_DAYS as current_streak,
                H.UNIT,
                H.BEST_STREAK
            FROM HABITS H
            LEFT JOIN HABIT_LOGS HL ON H.ID = HL.HABIT_ID 
                AND HL.LOG_DATE >= DATEADD(day, -?, GETDATE())
                AND HL.VALUE_ACHIEVED >= H.TARGET_VALUE
            WHERE H.USER_ID = ? AND H.IS_ACTIVE = 1
            GROUP BY H.ID, H.NAME, H.UNIT, H.STREAK_DAYS, H.BEST_STREAK
            ORDER BY H.STREAK_DAYS DESC
        """, (days, user_id))
        
        result = cursor.fetchall()
        print(f" Wynik zapytania: {len(result)} wierszy")
        for i, row in enumerate(result):
            print(f"🔍 Nawyk {i+1}: {row[0]}, passa: {row[3]}, najlepsza: {row[5]}")
        
        return result
        
    except Exception as e:
        print(f" Błąd przy pobieraniu statystyk: {e}")
        return []

def get_weekly_progress(user_id):
    """Pobiera progres z ostatnich 7 dni - zwraca więcej danych"""
    try:
        cursor.execute("""
            SELECT CONVERT(VARCHAR(10), HL.LOG_DATE, 120) as date,
                   COUNT(HL.ID) as habits_completed,
                   SUM(CASE WHEN HL.VALUE_ACHIEVED >= H.TARGET_VALUE THEN 1 ELSE 0 END) as goals_achieved,
                   COUNT(DISTINCT H.ID) as total_active_habits
            FROM HABIT_LOGS HL
            JOIN HABITS H ON HL.HABIT_ID = H.ID
            WHERE H.USER_ID = ? AND HL.LOG_DATE >= DATEADD(day, -7, GETDATE())
            GROUP BY HL.LOG_DATE
            ORDER BY HL.LOG_DATE DESC
        """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Błąd przy pobieraniu progresu tygodniowego: {e}")
        return []

# def get_category_success(user_id):
#     """Pobiera skuteczność według kategorii (dzisiejsze dane)"""
#     try:
#         cursor.execute("""
#             SELECT 
#                 CATEGORY,
#                 COUNT(*) as total_habits,
#                 SUM(CASE WHEN CURRENT_VALUE >= TARGET_VALUE THEN 1 ELSE 0 END) as completed_habits
#             FROM HABITS 
#             WHERE USER_ID = ? AND IS_ACTIVE = 1
#             GROUP BY CATEGORY
#         """, (user_id,))
#         return cursor.fetchall()
#     except Exception as e:
#         print(f"Błąd przy pobieraniu statystyk kategorii: {e}")
#         return []

def get_current_streak(user_id):
    """Oblicza aktualną passę użytkownika - kolejne dni z przynajmniej jednym wykonanym nawykiem"""
    try:
        cursor.execute("""
            SELECT DISTINCT LOG_DATE 
            FROM HABIT_LOGS HL
            JOIN HABITS H ON HL.HABIT_ID = H.ID
            WHERE H.USER_ID = ? AND HL.VALUE_ACHIEVED >= H.TARGET_VALUE
            ORDER BY LOG_DATE DESC
        """, (user_id,))

        
        dates = [row[0] for row in cursor.fetchall()] # stwórz listę dates biorąc pierwszy element z kazdego wiersza wyników
        
        if not dates:
            return 0
            
        # Sprawdź kolejne dni od najnowszego
        current_streak = 0
        today = datetime.now().date()
        current_date = today
        
        for i in range(len(dates)):
            if dates[i] == current_date:
                current_streak += 1
                current_date -= timedelta(days=1)
            else:
                break
                
        return current_streak
        
    except Exception as e:
        print(f"Błąd przy obliczaniu passy: {e}")
        return 0

def get_streak_history(user_id, days=7):
    """Pobiera historię passy - bazuje na kolejnych dniach z wykonanymi nawykami"""
    try:
        history = []
        today = datetime.now().date()
        days_pl = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd']
        
        # Pobierz dni z wykonanymi nawykami
        cursor.execute("""
            SELECT DISTINCT LOG_DATE
            FROM HABIT_LOGS HL
            JOIN HABITS H ON HL.HABIT_ID = H.ID
            WHERE H.USER_ID = ? AND HL.VALUE_ACHIEVED >= H.TARGET_VALUE
            AND HL.LOG_DATE >= DATEADD(day, -?, GETDATE())
            ORDER BY LOG_DATE DESC
        """, (user_id, days))
        
        completed_dates = {row[0] for row in cursor.fetchall()} # stwórz listę completed_dates biorąc pierwszy element z kazdego wiersza wyników
        
        for i in range(days-1, -1, -1):
            date = today - timedelta(days=i)
            day_of_week = days_pl[date.weekday()]
            
            completed = date in completed_dates
            
            if i == 0:
                day_label = "Dziś"
            else:
                day_label = day_of_week
            
            history.append({
                'date': date,
                'completed': completed,
                'day_label': day_label,
                'day_name': day_of_week,
                'is_today': i == 0
            })
        
        return history
        
    except Exception as e:
        print(f"Błąd przy pobieraniu historii passy: {e}")
        return []

def reset_habits_daily():
    """Automatycznie resetuje CURRENT_VALUE nawyków o północy"""
    try:
        today = datetime.now().date()
        
        cursor.execute("""
            UPDATE HABITS 
            SET CURRENT_VALUE = 0, LAST_RESET_DATE = ?
            WHERE (LAST_RESET_DATE IS NULL OR LAST_RESET_DATE < ?)
            AND IS_ACTIVE = 1
        """, (today, today))
        
        connection.commit()
        print(f"Zresetowano nawyki na dzień {today}")
        
    except Exception as e:
        print(f"Błąd przy resetowaniu nawyków: {e}")

# HOOKI I PROCESSORY

@app.before_request
def auto_reset_habits():
    """Automatycznie resetuje nawyki jeśli nowy dzień"""
    if current_user.is_authenticated:
        reset_habits_daily()

@app.context_processor
def utility_processor():
    def now():
        return datetime.now()
    
    def get_user_settings(user_id):
        """Pobiera ustawienia użytkownika"""
        try:
            cursor.execute("""
                SELECT DAILY_INSPIRATIONS, SHOW_NOTIFICATIONS, HANDLE 
                FROM USERS WHERE ID = ?
            """, (user_id,))
            return cursor.fetchone()
        except Exception as e:
            print(f"Błąd przy pobieraniu ustawień: {e}")
            return None
    
    return dict(now=now, get_user_settings=get_user_settings)

@app.after_request
def add_header(response):
    """Dodaj nagłówki zapobiegające cache'owaniu"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@login_manager.user_loader
def load_user(user_id):
    cursor.execute("SELECT ID, EMAIL, HANDLE, IS_ADMIN FROM USERS WHERE ID = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return User(row[0], row[1], row[2], bool(row[3]))
    return None

# ENDPOINTY - AUTORYZACJA

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/registration', methods = ['GET', 'POST'])
def registration():
    form = RegistrationForm()

    if form.validate_on_submit():
        cursor.execute('SELECT ID FROM USERS WHERE EMAIL = ?', (form.email.data,) )
        existing_email = cursor.fetchone()
        if existing_email:
            flash('Ten emial jest zajęty', 'warning')
            return render_template('registration.html', form=form)
        
        cursor.execute('SELECT ID FROM USERS WHERE HANDLE =?', (form.handle.data,))
        existing_handle = cursor.fetchone()
        if existing_handle:
            flash('Nazwa jest zajęta', 'warning')
            return render_template('registration.html', form=form)
        
        hashed_password = generate_password_hash(form.password.data)
        current_time = datetime.now()

        try: 
            cursor.execute('INSERT INTO USERS (EMAIL, PASSWORD, FIRSTNAME, LASTNAME, HANDLE, CREATED_DATE, MODIFIED_DATE) VALUES (?,?,?,?,?,?,?)',
                            (form.email.data, 
                            hashed_password, 
                            form.firstname.data, 
                            form.lastname.data, 
                            form.handle.data, 
                            current_time, 
                            current_time))
            
            connection.commit()
            flash('Rejestracja udana', 'success')
            return(redirect(url_for('login')))
        except Exception as e:
            connection.rollback()
            flash(f'Błąd rejestracji: {e}', 'error')
            return render_template('registration.html', form=form)
            
    return render_template('registration.html', form=form)

@app.route('/login', methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        cursor.execute('SELECT ID, EMAIL, PASSWORD, HANDLE, IS_ADMIN FROM USERS WHERE EMAIL =?', (form.email.data,))
        user_exist = cursor.fetchone()
        if user_exist:
            stored_hash = user_exist[2]
            if check_password_hash(stored_hash, form.password.data):
                user = User(user_exist[0], user_exist[1], user_exist[3], user_exist[4])
                login_user(user)
                flash('Zalogowano pomyślnie', 'success')
                return redirect(url_for('profile'))
            else:
                flash('Niepoprawne hasło', 'error')
        else:
            flash('Niepoprawny email', 'error')
    return render_template('login.html', form=form)

# ENDPOINTY - PROFIL I CELE

@app.route('/profile')
@login_required
def profile():
    # Pobierz aktywne główne cele
    cursor.execute("SELECT ID, NAME, DURATION_DAYS, CREATED, IS_ACTIVE FROM MAINGOALS WHERE USER_ID = ? AND IS_ACTIVE = 1 ORDER BY CREATED DESC", (current_user.id,))
    goals_raw = cursor.fetchall()

    goals = [
        {
            'id': g[0],
            'name': g[1],
            'duration_days': g[2],
            'created': g[3],
            'is_active': g[4]
        }
        for g in goals_raw
    ]

    # Pobierz aktywne wyzwania
    cursor.execute("""
        SELECT C.ID, C.NAME, S.NAME as SECTION_NAME, C.DURATION_DAYS, C.LEVEL, C.XP, UC.JoinedAt
        FROM CHALLENGES C
        JOIN SECTION S ON C.SECTION_ID = S.ID
        JOIN USERCHALLENGES UC ON C.ID = UC.CHALLENGEID
        WHERE UC.USERID = ? AND C.IS_ACTIVE = 1 AND UC.CompletedAt IS NULL
        ORDER BY UC.JoinedAt DESC
    """, (current_user.id,))
    challenges_raw = cursor.fetchall()

    joined_challenges = [
        {
            'id': c[0],
            'name': c[1],
            'section_name': c[2],
            'duration_days': c[3],
            'level': c[4],
            'xp': c[5],
            'joined_at': c[6]
        }
        for c in challenges_raw
    ]

    # Formularze
    add_form = MainGoalForm()
    edit_form = EditGoalForm()

    # ✅ Pobieramy aktualny progres LEVEL_POINTS i LEVEL_THRESHOLD
    cursor.execute("SELECT TOTAL_POINTS, CURRENT_LEVEL, LEVEL_POINTS, LEVEL_THRESHOLD FROM USERS WHERE ID = ?", (current_user.id,))
    user_data = cursor.fetchone()

    current_user.total_points = user_data[0]
    current_user.current_level = user_data[1]
    current_user.level_progress = user_data[2]
    current_user.level_max = user_data[3]
    # Obliczanie procent progresu  (dzielenie przez 0 lub None)
    progress = current_user.level_progress if current_user.level_progress is not None else 0
    maxp = current_user.level_max if current_user.level_max not in (None, 0) else 1

    current_user.level_pct = (progress / maxp) * 100
    current_user.level_pct = round(current_user.level_pct, 2)
    current_user.display_level = current_user.current_level

    # Pobranie odznak
    user_badges = get_user_badges(current_user.id)
    all_badges = get_all_badges()

    # Sprawdź czy czyścimy powiadomienie
    clear_notification = request.args.get('clear_notification')
    if clear_notification:
        session.pop('show_badge_notification', None)
        session.pop('new_badges', None)

        # Oblicz procent w Pythonie
  

    return render_template('profile.html', 
                         user=current_user, 
                         goals=goals, 
                         joined_challenges=joined_challenges,
                         user_badges=user_badges,
                         all_badges=all_badges,
                         add_form=add_form, 
                         edit_form=edit_form)

@app.route('/add_main_goal', methods=["POST"])
@login_required
def add_main_goal():
    form = MainGoalForm()
    if form.validate_on_submit():
        try:
            cursor.execute("INSERT INTO MAINGOALS (NAME, DURATION_DAYS, USER_ID, IS_ACTIVE, CREATED) VALUES (?,?,?,1,?)", 
                         (form.name.data, form.duration_days.data, current_user.id, datetime.now()))
            connection.commit()
            flash("Główny cel został dodany", 'success')
        except Exception as e:
            connection.rollback()
            flash(f"Błąd podczas dodawania celu: {e}", 'error')
    else:
        flash("Nie udało się dodać celu", 'error')
    return redirect(url_for('profile'))

@app.route('/update_goal', methods=['POST'])
@login_required
def update_goal():
    form = EditGoalForm()
    if form.validate_on_submit():
        try: 
            cursor.execute("UPDATE MAINGOALS SET NAME = ?, DURATION_DAYS = ? WHERE ID = ? AND USER_ID = ?", 
                         (form.name.data, form.duration_days.data, form.goal_id.data, current_user.id))
            connection.commit()
            flash("Cel został zaaktualizowany", 'success')
        except Exception as e: 
            connection.rollback()
            flash(f"Błąd przy aktualizacji celu: {e}", 'error')
    else:
        flash("Nie udało się zaaktualizować danych", 'error')
    return redirect(url_for('profile'))

@app.route('/complete_goal/<int:goal_id>', methods=['POST'])
@login_required
def complete_goal(goal_id):
    try:
        # Pobierz informacje o celu przed ukończeniem
        cursor.execute("SELECT NAME FROM MAINGOALS WHERE ID = ? AND USER_ID = ?", 
                     (goal_id, current_user.id))
        goal = cursor.fetchone()
        
        if goal:
            cursor.execute("UPDATE MAINGOALS SET IS_ACTIVE = 0, END_DATE = ? WHERE ID = ? AND USER_ID = ?", 
                         (datetime.now(), goal_id, current_user.id))
            connection.commit()
            # PUNKTY Z CELÓW SĄ PRYWATNE (NIE do rankingu)
            add_points_to_user(current_user.id, 350, source='goal')
            flash(f"Brawo! Ukończyłeś cel '{goal[0]}' i zdobyłeś 350 punktów", 'success')
        else:
            flash("Cel nie istnieje", 'error')
        
    except Exception as e:
        connection.rollback()
        flash(f"Błąd przy zakończeniu: {e}", 'error')
    return redirect(url_for('profile'))

@app.route('/reactivate_goal/<int:goal_id>', methods=['POST'])
@login_required
def reactivate_goal(goal_id):
    try:
        cursor.execute("UPDATE MAINGOALS SET IS_ACTIVE = 1, END_DATE = NULL WHERE ID = ? AND USER_ID = ?", 
                     (goal_id, current_user.id))
        connection.commit()
        flash("Cel został aktywowany", 'info')
    except Exception as e: 
        connection.rollback()
        flash(f"Nie udało się przywrócić celu: {e}", 'error')
    return redirect(url_for('profile'))

@app.route('/delete_goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_goal(goal_id):
    try: 
        cursor.execute("DELETE FROM MAINGOALS WHERE ID = ? AND USER_ID = ?", 
                     (goal_id, current_user.id))
        connection.commit()
        flash("Cel został usunięty", 'warning')
    except Exception as e:
        connection.rollback()
        flash(f"Nie udało się usunąć celu: {e}", 'error')
    return redirect(url_for('profile'))

# =============================================================================
# ENDPOINTY - WYZWANIA
# =============================================================================

@app.route('/challenges')
@login_required
def challenges():
    #Pobieramy wybrany poziom z filtru
    selected_level = request.args.get('level', 'all')

    #Podstawowe zapytanie
    query = """SELECT C.ID, C.NAME, C.SECTION_ID, S.NAME, C.DURATION_DAYS, C.LEVEL, C.XP
                FROM CHALLENGES C
                JOIN SECTION S ON C.SECTION_ID = S.ID
                WHERE C.IS_ACTIVE = 1"""
    
    if selected_level != 'all':
        query += "AND C.LEVEL = ?"
        params = (selected_level,)
    else:
        params = ()

    cursor.execute(query, params)
    data = cursor.fetchall()

    challenges_by_section = {}
    for row in data:
        challenge_id, challenge_name, section_id, section_name, duration_days, level, xp = row

        if section_name not in challenges_by_section:
            challenges_by_section[section_name] = []

        challenges_by_section[section_name].append({
            "id": challenge_id,
            "name": challenge_name,
            "duration_days": duration_days,
            "level": level,
            "xp": xp
        })
    return render_template('challenges.html', user=current_user, challenges=challenges_by_section, selected_level=selected_level)

@app.route('/join_challenge/<int:challenge_id>', methods=['POST'])
@login_required
def join_challenge(challenge_id):
    try:
        cursor.execute("SELECT * FROM USERCHALLENGES WHERE USERID = ? AND CHALLENGEID = ?", (current_user.id, challenge_id))
        existing = cursor.fetchone()

        if existing:
            flash("Już dołączyłeś do tego wyzwania", 'warning')
            return redirect(url_for('challenges'))
        
        cursor.execute("INSERT INTO USERCHALLENGES (USERID, CHALLENGEID, JoinedAt) VALUES (?, ?, ?)", 
                     (current_user.id, challenge_id, datetime.now()))
        connection.commit()
        flash("Dołączyłeś do wyzwania", 'success')
        
    except Exception as e:
        connection.rollback()
        flash(f"Błąd przy dołączeniu: {e}", 'error')
    return redirect(url_for('challenges'))

@app.route('/complete_challenge/<int:challenge_id>', methods=['POST'])
@login_required
def complete_challenge(challenge_id):
    try:
        cursor.execute("""SELECT C.XP, UC.CompletedAt 
                       FROM CHALLENGES C
                       JOIN USERCHALLENGES UC ON C.ID = UC.CHALLENGEID
                       WHERE UC.USERID = ? AND UC.CHALLENGEID = ?""", 
                     (current_user.id, challenge_id))
        result = cursor.fetchone()
        
        if result and not result[1]:
            challenge_xp = result[0]
            cursor.execute("UPDATE USERCHALLENGES SET CompletedAt = ? WHERE USERID = ? AND CHALLENGEID = ?", 
                         (datetime.now(), current_user.id, challenge_id))
            
            # PUNKTY Z WYZWAŃ IDĄ DO RANKINGU
            add_points_to_user(current_user.id, challenge_xp, source='challenge')
            connection.commit()
            flash(f"Wyzwanie ukończone! Zdobyto {challenge_xp} punktów rankingowych!", 'success')
        else:
            flash("Wyzwanie nie istnieje lub już je ukończyłeś", 'warning')
            
    except Exception as e:
        connection.rollback()
        flash(f"Błąd przy ukończeniu wyzwania: {e}", 'error')
    return redirect(url_for('profile'))

# =============================================================================
# ENDPOINTY - ADMIN
# =============================================================================

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Nie masz uprawnień", 'error')
        return redirect(url_for('profile'))
    
    cursor.execute("SELECT ID, NAME FROM SECTION")
    sections = cursor.fetchall()
    
    section_form = SectionForm()
    challenge_form = ChallengeForm()
    challenge_form.section_id.choices = [(s[0], s[1]) for s in sections]
    return render_template('admin_panel.html', 
                           section_form=section_form, 
                           challenge_form=challenge_form,
                           user=current_user)

@app.route('/add_section', methods=['POST'])
@login_required
def add_section():
    if not current_user.is_admin:
        flash("Brak uprawnień", 'error')
        return redirect(url_for('profile'))
    
    form = SectionForm()
    if form.validate_on_submit():
        cursor.execute("INSERT INTO SECTION (NAME) VALUES (?)", (form.name.data,))
        connection.commit()
        flash("Sekcja została dodana!", 'success')
    else:
        flash("Błąd w formularzu sekcji.", 'error')
    return redirect(url_for('admin_panel'))

@app.route('/add_challenge', methods=['POST'])
@login_required
def add_challenge():
    if not current_user.is_admin:
        flash("Brak uprawnień", 'error')
        return redirect(url_for('index'))
    
    form = ChallengeForm()
    cursor.execute("SELECT ID, NAME FROM SECTION")
    form.section_id.choices = [(s[0], s[1]) for s in cursor.fetchall()]
    
    if form.validate_on_submit():
        cursor.execute("""
            INSERT INTO CHALLENGES (NAME, SECTION_ID, DURATION_DAYS, LEVEL, XP, IS_ACTIVE)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (form.name.data, form.section_id.data, form.duration_days.data,
              form.level.data, form.xp.data, int(form.is_active.data)))
        connection.commit()
        flash("Wyzwanie zostało dodane!", 'success')
    else:
        flash("Błąd w formularzu wyzwania.", 'error')
    return redirect(url_for('admin_panel'))

# =============================================================================
# ENDPOINTY - NAWYKI
# =============================================================================

@app.route('/habits')
@login_required
def habits():
    """Strona z nawykami użytkownika"""
    # Sprawdź czy czyścimy powiadomienie
    clear_notification = request.args.get('clear_notification')
    if clear_notification:
        session.pop('show_badge_notification', None)
        session.pop('new_badges', None)
        return redirect(url_for('habits'))
    
    user_habits = get_user_habits(current_user.id)
    habit_form = HabitForm()
    progress_form = HabitProgressForm()
    
    # Sprawdź czy pokazać inspiracje
    daily_inspiration = None
    user_settings = get_user_settings(current_user.id)
    
    
    if user_settings and user_settings[0]:  # DAILY_INSPIRATIONS = True
        daily_inspiration = get_daily_inspiration()
        

    return render_template('habits.html',
                         user=current_user,
                         habits=user_habits,
                         habit_form=habit_form,
                         progress_form=progress_form,
                         daily_inspiration=daily_inspiration)

@app.route('/add_habit', methods=['POST'])
@login_required
def add_habit():
    """Dodaje nowy nawyk - BEZ IKON"""
    form = HabitForm()
    if form.validate_on_submit():
        try:
            cursor.execute("""
                INSERT INTO HABITS (USER_ID, NAME, DESCRIPTION, TARGET_VALUE, UNIT, CATEGORY, COLOR)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (current_user.id, form.name.data, form.description.data, 
                  form.target_value.data, form.unit.data, form.category.data,
                  form.color.data or '#3B82F6'))  # USUNIĘTO ICON
            connection.commit()
            flash('Nawyk został dodany!', 'success')
        except Exception as e:
            connection.rollback()
            flash(f'Błąd przy dodawaniu nawyku: {e}', 'error')
    else:
        flash('Błąd w formularzu', 'error')
    
    return redirect(url_for('habits'))

@app.route('/update_habit_progress/<int:habit_id>', methods=['POST'])
@login_required
def update_habit_progress_route(habit_id):
    """Aktualizuje progres nawyku"""
    form = HabitProgressForm()
    if form.validate_on_submit():
        success = update_habit_progress(habit_id, form.value_achieved.data)
        if success:
            flash('Progres zaktualizowany!', 'success')
        else:
            flash('Błąd przy aktualizacji progresu', 'error')
    else:
        flash('Nieprawidłowa wartość', 'error')
    
    return redirect(url_for('habits'))

@app.route('/reset_habit/<int:habit_id>', methods=['POST'])
@login_required
def reset_habit(habit_id):
    """Resetuje nawyk i odejmuje punkty za dzisiejsze osiągnięcie"""
    try:
        # Sprawdź czy nawyk miał dzisiaj osiągnięty cel
        cursor.execute("""
            SELECT CURRENT_VALUE, TARGET_VALUE, NAME, STREAK_DAYS, BEST_STREAK
            FROM HABITS WHERE ID = ? AND USER_ID = ?
        """, (habit_id, current_user.id))
        
        habit_data = cursor.fetchone()
        if not habit_data:
            flash('Nawyk nie istnieje', 'error')
            return redirect(url_for('habits'))
            
        current_value, target_value, habit_name, streak_days, best_streak = habit_data
        
        # Odejmij punkty tylko jeśli cel był osiągnięty dzisiaj
        points_to_remove = 0
        if current_value >= target_value:
            points_to_remove = 10  # DOKŁADNIE TYLE SAMO CO PRZY DODAWANIU
            remove_points_from_user(current_user.id, points_to_remove, source='habit')
        
        # Zresetuj nawyk - TERAZ RÓWNIEŻ BEST_STREAK
        cursor.execute("""
            UPDATE HABITS 
            SET CURRENT_VALUE = 0, STREAK_DAYS = 0, BEST_STREAK = 0
            WHERE ID = ? AND USER_ID = ?
        """, (habit_id, current_user.id))
        
        cursor.execute("DELETE FROM HABIT_LOGS WHERE HABIT_ID = ?", (habit_id,))
        connection.commit()
        
        # Debug info
        print(f"🔍 RESET: {habit_name}, passa: {streak_days} → 0, najlepsza: {best_streak} → 0")
        
        if points_to_remove > 0:
            flash(f'Nawyk "{habit_name}" zresetowany! Odebrano {points_to_remove} punktów.', 'warning')
        else:
            flash(f'Nawyk "{habit_name}" zresetowany!', 'info')
        
    except Exception as e:
        connection.rollback()
        print(f"❌ Błąd przy resetowaniu: {e}")
        flash(f'Błąd przy resetowaniu: {e}', 'error')
    
    return redirect(url_for('habits'))

@app.route('/toggle_habit/<int:habit_id>', methods=['POST'])
@login_required
def toggle_habit(habit_id):
    """Aktywuje/deaktywuje nawyk - DEAKTYWOWANE NIE POKAZUJĄ SIĘ W DASHBOARD"""
    try:
        cursor.execute("SELECT IS_ACTIVE FROM HABITS WHERE ID = ? AND USER_ID = ?", 
                     (habit_id, current_user.id))
        habit = cursor.fetchone()
        
        if habit:
            new_status = not habit[0]
            cursor.execute("UPDATE HABITS SET IS_ACTIVE = ? WHERE ID = ?", 
                         (new_status, habit_id))
            connection.commit()
            
            status_text = "aktywowany" if new_status else "deaktywowany"
            flash(f'Nawyk {status_text}!', 'success')
        else:
            flash('Nawyk nie istnieje', 'error')
            
    except Exception as e:
        connection.rollback()
        flash(f'Błąd: {e}', 'error')
    
    return redirect(url_for('habits'))

# =============================================================================
# ENDPOINTY - DASHBOARD I STATYSTYKI
# =============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard z podsumowaniem i statystykami"""
    # Sprawdź czy czyścimy powiadomienie
    clear_notification = request.args.get('clear_notification')
    if clear_notification:
        session.pop('show_badge_notification', None)
        session.pop('new_badges', None)
        return redirect(url_for('dashboard'))
    
    # ✅ Pobierz aktualne punkty użytkownika
    cursor.execute("SELECT TOTAL_POINTS, CURRENT_LEVEL, LEVEL_POINTS, LEVEL_THRESHOLD FROM USERS WHERE ID = ?", (current_user.id,))
    user_data = cursor.fetchone()

    current_user.total_points = user_data[0] or 0
    current_user.current_level = user_data[1] or 1
    current_user.level_progress = user_data[2] or 0
    current_user.level_max = user_data[3] or 250
    
    # Statystyki nawyków
    habit_stats = get_habit_stats(current_user.id)
    weekly_progress = get_weekly_progress(current_user.id)
    # category_stats = get_category_success(current_user.id)
    current_streak = get_current_streak(current_user.id)
    streak_history = get_streak_history(current_user.id)
    
    # Pobierz odznaki użytkownika
    user_badges = get_user_badges(current_user.id)
    
    return render_template('dashboard.html',
                         user=current_user,
                         habit_stats=habit_stats,
                         weekly_progress=weekly_progress,
                        #  category_stats=category_stats,
                         current_streak=current_streak,
                         streak_history=streak_history,
                         user_badges=user_badges)

# =============================================================================
# ENDPOINTY - HISTORIA I RANKING
# =============================================================================

@app.route('/history')
@login_required
def history():
    # Pobierz parametr filtru z URL
    filter_type = request.args.get('filter', 'all')  # all, goals, challenges, habits
    """Strona z historią - ukończone cele, wyzwania i nieaktywne nawyki"""
    completed_goals = get_completed_goals(current_user.id)
    completed_challenges = get_completed_challenges(current_user.id)
    
    # Pobierz nieaktywne nawyki
    try:
        cursor.execute("""
            SELECT ID, NAME, DESCRIPTION, TARGET_VALUE, CURRENT_VALUE, UNIT, 
                   CATEGORY, COLOR, STREAK_DAYS, BEST_STREAK, IS_ACTIVE
            FROM HABITS 
            WHERE USER_ID = ? AND IS_ACTIVE = 0
            ORDER BY CREATED_DATE DESC
        """, (current_user.id,))
        inactive_habits = cursor.fetchall()
    except Exception as e:
        print(f"Błąd przy pobieraniu nieaktywnych nawyków: {e}")
        inactive_habits = []
    
    return render_template('history.html',
                         user=current_user,
                         completed_goals=completed_goals,
                         completed_challenges=completed_challenges,
                         inactive_habits=inactive_habits,
                        filter_type=filter_type)

@app.route('/activate_habit/<int:habit_id>', methods=['POST'])
@login_required
def activate_habit(habit_id):
    """Aktywuje nieaktywny nawyk z historii"""
    try:
        cursor.execute("""
            UPDATE HABITS 
            SET IS_ACTIVE = 1 
            WHERE ID = ? AND USER_ID = ? AND IS_ACTIVE = 0
        """, (habit_id, current_user.id))
        
        if cursor.rowcount > 0:
            connection.commit()
            flash('Nawyk został aktywowany!', 'success')
        else:
            flash('Nie znaleziono nieaktywnego nawyku', 'error')
            
    except Exception as e:
        connection.rollback()
        print(f"Błąd przy aktywowaniu nawyku: {e}")
        flash(f'Błąd przy aktywowaniu nawyku: {e}', 'error')
    
    return redirect(url_for('history'))

@app.route('/delete_habit_permanently/<int:habit_id>', methods=['POST'])
@login_required
def delete_habit_permanently(habit_id):
    """Trwale usuwa nieaktywny nawyk z historii"""
    try:
        # Najpierw usuń historię
        cursor.execute("DELETE FROM HABIT_LOGS WHERE HABIT_ID = ?", (habit_id,))
        
        # Potem usuń nawyk
        cursor.execute("DELETE FROM HABITS WHERE ID = ? AND USER_ID = ?", (habit_id, current_user.id))
        
        if cursor.rowcount > 0:
            connection.commit()
            flash('Nawyk został trwale usunięty!', 'success')
        else:
            flash('Nie znaleziono nawyku', 'error')
            
    except Exception as e:
        connection.rollback()
        print(f"Błąd przy usuwaniu nawyku: {e}")
        flash(f'Błąd przy usuwaniu nawyku: {e}', 'error')
    
    return redirect(url_for('history'))

@app.route('/ranking')
@login_required
def ranking():
    top_users = get_top_users(10)
    return render_template('ranking.html', 
                         user=current_user,
                         top_users=top_users)

# =============================================================================
# ENDPOINTY - USTAWIENIA
# =============================================================================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    form = UserSettingsForm()
    
    # Pobierz aktualne ustawienia użytkownika
    current_settings = get_user_settings(current_user.id)
    
    # Jeśli to GET, wczytaj aktualne dane do formularza
    if request.method == 'GET':
        if current_settings:
            form.daily_inspirations.data = bool(current_settings[0])
            form.show_notifications.data = bool(current_settings[1])
            form.handle.data = current_settings[2] or current_user.handle
    
    if form.validate_on_submit():
        try:
            # Sprawdź czy nazwa użytkownika jest dostępna
            if form.handle.data != current_user.handle:
                cursor.execute('SELECT id FROM USERS WHERE HANDLE = ? AND ID != ?', 
                             (form.handle.data, current_user.id))
                existing_handle = cursor.fetchone()
                if existing_handle:
                    flash('Ta nazwa użytkownika jest już zajęta', 'error')
                    return render_template('settings.html', form=form, user=current_user)
            
            # Przygotuj zapytanie UPDATE
            update_fields = []
            params = []
            
            update_fields.append("HANDLE = ?")
            params.append(form.handle.data)
            
            update_fields.append("DAILY_INSPIRATIONS = ?")
            params.append(int(form.daily_inspirations.data))
            
            update_fields.append("SHOW_NOTIFICATIONS = ?")
            params.append(int(form.show_notifications.data))
            
            # DODAJ AKTUALIZACJĘ DATY MODYFIKACJI
            update_fields.append("MODIFIED_DATE = ?")
            params.append(datetime.now())
            
            # Jeśli użytkownik podał nowe hasło
            if form.new_password.data:
                hashed_password = generate_password_hash(form.new_password.data)
                update_fields.append("PASSWORD = ?")
                params.append(hashed_password)
            
            params.append(current_user.id)
            
            # Wykonaj aktualizację
            query = f"UPDATE USERS SET {', '.join(update_fields)} WHERE ID = ?"
            cursor.execute(query, params)
            
            connection.commit()
            
            # Aktualizuj dane w sesji
            current_user.handle = form.handle.data
            
            flash('Ustawienia zapisane pomyślnie!', 'success')
            return redirect(url_for('settings'))
            
        except Exception as e:
            connection.rollback()
            flash(f' Błąd przy zapisywaniu ustawień: {e}', 'error')
    
    return render_template('settings.html', form=form, user=current_user)

# =============================================================================
# URUCHOMIENIE APLIKACJI
# =============================================================================

if __name__ == '__main__':
    app.run(debug=True)