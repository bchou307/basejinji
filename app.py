from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from openai import AzureOpenAI  # TextAnalyticsClientではなくAzureOpenAIをインポート
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.username = username

def load_users():
    users = {}
    try:
        with open('users', 'r') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    username, password = line.split(':', 1)
                    users[username] = password
    except FileNotFoundError:
        print("users file not found")
    return users

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        return User(user_id)
    return None

# Azure OpenAI設定
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")  # デプロイ名
AZURE_OPENAI_API_VERSION = "2024-02-15-preview"  # APIバージョン:cite[4]

def get_azure_openai_client():
    """Azure OpenAIクライアントを取得"""
    client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version=AZURE_OPENAI_API_VERSION
    )
    return client

# 日本語フォントの登録（以前と同じ）
def register_japanese_font():
    try:
        # 様々なOSのフォントパスを試す
        font_paths = [
            "C:/Windows/Fonts/msgothic.ttc",  # Windows
            "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",  # macOS
            "/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf",  # Linux
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('Japanese', font_path))
                print(f"日本語フォントを登録しました: {font_path}")
                return True
        
        print("日本語フォントが見つかりませんでした")
        return False
        
    except Exception as e:
        print(f"フォント登録エラー: {e}")
        return False

# アプリ起動時にフォント登録
font_registered = register_japanese_font()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('menu'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        
        if username in users and users[username] == password:
            user = User(username)
            login_user(user)
            return redirect(url_for('menu'))
        else:
            return render_template('login.html', error='ユーザー名またはパスワードが正しくありません')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def menu():
    return render_template('menu.html')

@app.route('/agenda')
@login_required
def agenda():
    return render_template('index.html')

@app.route('/resume')
@login_required
def resume():
    return render_template('resume.html')

@app.route('/generate', methods=['POST'])
@login_required
def generate_agenda():
    data = {
        'personality': request.form.get('personality'),
        'role': request.form.get('role'),
        'skills': request.form.get('skills'),
        'experience': request.form.get('experience'),
        'career_goal': request.form.get('career_goal'),
        'motivation': request.form.get('motivation'),
        'additional_notes': request.form.get('additional_notes', '')
    }
    
    agenda_content = generate_agenda_with_ai(data)
    pdf_buffer = generate_pdf(agenda_content, data)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name='1on1_agenda.pdf',
        mimetype='application/pdf'
    )

def generate_agenda_with_ai(data):
    """Azure OpenAIを使用してアジェンダを生成"""
    try:
        client = get_azure_openai_client()
        
        # プロンプトの作成
        prompt = f"""
        以下の部員情報に基づいて、部長と部員の1on1面談の詳細なアジェンダを作成してください。
        アジェンダは以下の構成で、具体的な質問例や議論ポイントを含めてください。

        部員情報:
        - 性格・タイプ: {data['personality']}
        - 作業状況・役割: {data['role']}
        - 技術力・スキル: {data['skills']}
        - 入社年数・経験: {data['experience']}
        - キャリア志向・希望: {data['career_goal']}
        - モチベーション・価値観: {data['motivation']}
        - 追加メモ: {data['additional_notes']}

        アジェンダ構成:
        1. 前回の目標振り返りと進捗確認
        2. 現在の業務状況と課題
        3. スキル開発と成長機会
        4. キャリアパスと将来の目標
        5. 支援必要な事項とリソース
        6. 次回までの目標設定

        各項目について具体的な質問例も含めてください。
        """
        
        # Azure OpenAI APIを呼び出し:cite[5]:cite[8]
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,  # デプロイ名を指定:cite[8]
            messages=[
                {"role": "system", "content": "あなたは優秀な人事部のアシスタントです。1on1面談のアジェンダを作成する専門家です。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return f"AI処理中にエラーが発生しました: {str(e)}"

def generate_pdf(content, data):
    """PDF生成関数（以前と同じ）"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # 日本語用スタイルの定義
    if font_registered:
        font_name = 'Japanese'
    else:
        font_name = 'Helvetica'
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=font_name,
        fontSize=16,
        spaceAfter=30
    )
    
    info_style = ParagraphStyle(
        'CustomInfo',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        spaceAfter=12
    )
    
    content_style = ParagraphStyle(
        'CustomContent',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=12,
        spaceAfter=12
    )
    
    # タイトル
    story.append(Paragraph("1on1面談アジェンダ", title_style))
    story.append(Spacer(1, 20))
    
    # 基本情報
    info_text = f"""
    <b>性格・タイプ:</b> {data['personality']}<br/>
    <b>作業状況・役割:</b> {data['role']}<br/>
    <b>技術力・スキル:</b> {data['skills']}<br/>
    <b>入社年数・経験:</b> {data['experience']}<br/>
    <b>キャリア志向:</b> {data['career_goal']}<br/>
    <b>モチベーション:</b> {data['motivation']}
    """
    
    story.append(Paragraph(info_text, info_style))
    story.append(Spacer(1, 20))
    
    # アジェンダ内容
    formatted_content = content.replace('\n', '<br/>')
    story.append(Paragraph(formatted_content, content_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
