from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import psycopg2
import psycopg2.extras
import hashlib
import re
import os
import secrets
import logging
from datetime import datetime, date

app = Flask(__name__)

# ========== CONFIGURAÇÃO DE SEGURANÇA ==========
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print("⚠️ SECRET_KEY não encontrada. Usando valor gerado.")
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True  # Alterado para True em produção
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 horas
app.config['SESSION_COOKIE_DOMAIN'] = None  # Permitir em qualquer domínio

# ========== CONFIGURAÇÃO DO BANCO NEON.TECH ==========
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    # Fallback apenas para desenvolvimento local
    DATABASE_URL = 'postgresql://neondb_owner:npg_hJ6VyeWsKHf0@ep-restless-bush-ai3wlmz2-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require'
    print("⚠️ DATABASE_URL não encontrada. Usando string de conexão local.")

def get_db_connection():
    """Cria conexão com o Neon.tech"""
    try:
        # Garantir que sslmode está configurado corretamente
        if 'sslmode' not in DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL + '?sslmode=require')
        else:
            conn = psycopg2.connect(DATABASE_URL)
        
        # Testar a conexão
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        
        print("✅ Conexão com banco de dados estabelecida")
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao Neon.tech: {e}")
        return None

def criar_tabelas():
    """Cria as tabelas necessárias"""
    conn = get_db_connection()
    if not conn:
        print("❌ Não foi possível conectar ao banco")
        return False
    
    try:
        cursor = conn.cursor()
        
        # Tabela usuario
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuario (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(100) NOT NULL,
                telefone VARCHAR(20) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                senha VARCHAR(255) NOT NULL,
                data_nascimento DATE NOT NULL,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ultimo_login TIMESTAMP,
                ativo BOOLEAN DEFAULT TRUE
            )
        """)
        
        # Tabela recuperacao_senha
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recuperacao_senha (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                token VARCHAR(64) UNIQUE NOT NULL,
                usado BOOLEAN DEFAULT FALSE,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expira_em TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES usuario(id) ON DELETE CASCADE
            )
        """)
        
        # Índices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usuario_email ON usuario(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recuperacao_token ON recuperacao_senha(token)")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Tabelas criadas/verificadas com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao criar tabelas: {e}")
        if conn:
            conn.close()
        return False

# ========== FUNÇÕES AUXILIARES ==========

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_date(date_string):
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def calcular_idade(data_nascimento_str):
    try:
        data_nascimento = datetime.strptime(data_nascimento_str, '%Y-%m-%d').date()
        hoje = date.today()
        idade = hoje.year - data_nascimento.year
        if (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day):
            idade -= 1
        return idade
    except:
        return 0

# ========== ROTAS ==========

@app.route('/')
def index():
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/cadastro')
def cadastro_page():
    hoje = date.today()
    max_date = hoje.replace(year=hoje.year - 15)
    min_date = hoje.replace(year=hoje.year - 120)
    return render_template('cadastro.html', 
                         max_date=max_date.strftime('%Y-%m-%d'),
                         min_date=min_date.strftime('%Y-%m-%d'))

# ========== API DE VERIFICAÇÃO DE IDADE ==========

@app.route('/api/verificar-idade', methods=['POST'])
def verificar_idade():
    try:
        data_nascimento = request.form.get('data_nascimento', '').strip()
        
        if not data_nascimento:
            return jsonify({'success': False, 'message': 'Informe uma data de nascimento'}), 400
        
        if not validate_date(data_nascimento):
            return jsonify({'success': False, 'message': 'Data de nascimento inválida!'}), 400
        
        idade = calcular_idade(data_nascimento)
        idade_minima = 15
        idade_valida = idade >= idade_minima
        
        return jsonify({
            'success': True,
            'idade': idade,
            'idade_valida': idade_valida,
            'mensagem': f"Idade: {idade} anos - {'Válido' if idade_valida else 'Inválido'}"
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ========== API DE CADASTRO ==========

@app.route('/api/cadastrar', methods=['POST'])
def cadastrar_usuario():
    try:
        nome = request.form.get('nome', '').strip()
        telefone = request.form.get('telefone', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '').strip()
        data_nascimento = request.form.get('data_nascimento', '').strip()
        
        if not all([nome, telefone, email, senha, data_nascimento]):
            return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios!'}), 400
        
        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Email inválido!'}), 400
        
        idade = calcular_idade(data_nascimento)
        if idade < 15:
            return jsonify({'success': False, 'message': f'Idade mínima: 15 anos. Sua idade: {idade} anos'}), 400
        
        if len(senha) < 6:
            return jsonify({'success': False, 'message': 'A senha deve ter no mínimo 6 caracteres!'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Erro de conexão com o banco!'}), 500
        
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM usuario WHERE email = %s", (email,))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'Email já cadastrado!'}), 400
            
            senha_hash = hash_password(senha)
            
            cursor.execute("""
                INSERT INTO usuario (nome, telefone, email, senha, data_nascimento)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, nome, email
            """, (nome, telefone, email, senha_hash, data_nascimento))
            
            user_id, user_nome, user_email = cursor.fetchone()
            conn.commit()
            
            session['user_id'] = user_id
            session['user_nome'] = user_nome
            session['user_email'] = user_email
            session['logged_in'] = True
            session.permanent = True
            
            return jsonify({
                'success': True,
                'message': 'Cadastro realizado com sucesso!',
                'user': {'id': user_id, 'nome': user_nome, 'email': user_email}
            })
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'message': 'Erro interno do servidor!'}), 500

# ========== API DE LOGIN ==========

@app.route('/api/login', methods=['POST'])
def login():
    try:
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '').strip()
        
        if not email or not senha:
            return jsonify({'success': False, 'message': 'Email e senha são obrigatórios!'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Erro de conexão!'}), 500
        
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, nome, email, senha 
                FROM usuario 
                WHERE email = %s
            """, (email,))
            
            usuario = cursor.fetchone()
            
            if not usuario:
                return jsonify({'success': False, 'message': 'Email não cadastrado!'}), 401
            
            user_id, nome, user_email, senha_hash = usuario
            
            if senha_hash != hash_password(senha):
                return jsonify({'success': False, 'message': 'Senha incorreta!'}), 401
            
            cursor.execute("UPDATE usuario SET ultimo_login = CURRENT_TIMESTAMP WHERE id = %s", (user_id,))
            conn.commit()
            
            session['user_id'] = user_id
            session['user_nome'] = nome
            session['user_email'] = user_email
            session['logged_in'] = True
            session.permanent = True
            
            return jsonify({
                'success': True,
                'message': 'Login realizado com sucesso!',
                'user': {'id': user_id, 'nome': nome, 'email': user_email}
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'message': 'Erro interno!'}), 500

# ========== API DE LOGOUT ==========

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logout realizado com sucesso!'})

@app.route('/api/check-session', methods=['GET'])
def check_session():
    if 'user_id' in session and session.get('logged_in'):
        return jsonify({
            'authenticated': True,
            'user': {
                'id': session['user_id'],
                'nome': session['user_nome'],
                'email': session['user_email']
            }
        })
    return jsonify({'authenticated': False})

# ========== DASHBOARD ==========

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or not session.get('logged_in'):
        return redirect(url_for('login_page'))
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                height: 100vh;
                margin: 0;
                display: flex;
                justify-content: center;
                align-items: center;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                max-width: 500px;
                width: 90%;
                text-align: center;
            }}
            h1 {{ color: #333; }}
            button {{
                padding: 12px 30px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Bem-vindo, {session.get('user_nome')}!</h1>
            <p>Email: {session.get('user_email')}</p>
            <button onclick="logout()">Sair</button>
        </div>
        <script>
            async function logout() {{
                try {{
                    const response = await fetch('/api/logout', {{ 
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json'
                        }}
                    }});
                    if (response.ok) {{
                        window.location.href = '/login';
                    }}
                }} catch (error) {{
                    console.error('Erro ao fazer logout:', error);
                    window.location.href = '/login';
                }}
            }}
        </script>
    </body>
    </html>
    """

# ========== ROTA DE SAÚDE ==========

@app.route('/health')
def health():
    conn = get_db_connection()
    db_status = 'connected' if conn else 'disconnected'
    if conn:
        conn.close()
    return jsonify({
        'status': 'healthy',
        'database': db_status,
        'timestamp': datetime.now().isoformat()
    })

# ========== ROTA PARA VERIFICAR CONFIGURAÇÃO ==========

@app.route('/config-check')
def config_check():
    """Rota auxiliar para verificar configurações (apenas para debug)"""
    return jsonify({
        'database_configured': DATABASE_URL is not None,
        'secret_key_configured': app.secret_key is not None,
        'environment': 'production' if os.environ.get('RENDER') else 'development'
    })

# ========== INICIALIZAÇÃO ==========

# Criar tabelas ao iniciar a aplicação (tanto local quanto no Render)
with app.app_context():
    tabelas_criadas = criar_tabelas()
    if tabelas_criadas:
        print("✅ Banco de dados inicializado com sucesso!")
    else:
        print("⚠️ Problema ao inicializar banco de dados. Verifique a conexão.")

# Configurar logging para produção
if os.environ.get('RENDER'):
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    print("🚀 Aplicação iniciada no Render com configurações de produção")
else:
    print("🚀 Aplicação iniciada em modo desenvolvimento")

if __name__ == '__main__':
    # Rodando localmente
    print("🚀 Servidor rodando em http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
