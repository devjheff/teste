from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import psycopg2
import hashlib
import re
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = '12345'

# Configurações do banco de dados
banco_de_dados = {
    'host': 'localhost',
    'database': 'postgres',
    'user': 'postgres',
    'password': '123',
    'port': '5433'
}

def hash_password(password):
    """Cria hash da senha usando SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash, provided_password):
    """Verifica se a senha fornecida corresponde ao hash armazenado"""
    return hash_password(provided_password) == stored_hash

def validate_email(email):
    """Valida formato do email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_date(date_string):
    """Valida formato da data (YYYY-MM-DD)"""
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def calcular_idade(data_nascimento_str):
    """
    Calcula a idade a partir da data de nascimento
    Formato esperado: YYYY-MM-DD
    Retorna a idade em anos (int)
    """
    try:
        # Converter string para objeto date
        data_nascimento = datetime.strptime(data_nascimento_str, '%Y-%m-%d').date()
        hoje = date.today()
        
        # Calcular diferença de anos
        idade = hoje.year - data_nascimento.year
        
        # Ajustar se ainda não fez aniversário este ano
        # Compara mês e dia atual com mês e dia de nascimento
        if (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day):
            idade -= 1
        
        return idade
    except Exception as e:
        print(f"Erro ao calcular idade: {e}")
        return 0  # Retorna 0 em caso de erro

def get_db_connection():
    """Cria conexão com o banco de dados"""
    try:
        conn = psycopg2.connect(**banco_de_dados)
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        return None

def criar_tabela():
    """Cria a tabela se não existir (SEM campo idade)"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            create_table_query = """
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
            """
            cursor.execute(create_table_query)
            conn.commit()
            cursor.close()
            conn.close()
            print("✓ Tabela 'usuario' criada/verificada com sucesso!")
        except Exception as e:
            print(f"✗ Erro ao criar tabela: {e}")
            if conn:
                conn.close()
    else:
        print("✗ Não foi possível conectar ao banco para criar a tabela")

# ========== ROTAS ==========

@app.route('/')
def index():
    """Rota principal"""
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    """Página de login"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/cadastro')
def cadastro_page():
    """Página de cadastro"""
    # Configurar datas limites para o formulário
    hoje = date.today()
    max_date = hoje.replace(year=hoje.year - 15)  # Mínimo 15 anos
    min_date = hoje.replace(year=hoje.year - 120)  # Máximo 120 anos
    
    return render_template('cadastro.html', 
                         max_date=max_date.strftime('%Y-%m-%d'),
                         min_date=min_date.strftime('%Y-%m-%d'))

# ========== NOVA ROTA PARA VERIFICAR IDADE ==========

@app.route('/api/verificar-idade', methods=['POST'])
def verificar_idade():
    """API para verificar se o usuário tem 15 anos ou mais"""
    try:
        data_nascimento = request.form.get('data_nascimento', '').strip()
        
        if not data_nascimento:
            return jsonify({
                'success': False,
                'message': 'Informe uma data de nascimento'
            }), 400
        
        if not validate_date(data_nascimento):
            return jsonify({
                'success': False,
                'message': 'Data de nascimento inválida! Use o formato YYYY-MM-DD'
            }), 400
        
        # Calcular idade
        idade = calcular_idade(data_nascimento)
        
        # Verificar se tem 15 anos ou mais
        idade_minima = 15
        idade_valida = idade >= idade_minima
        
        # Preparar mensagem
        if idade_valida:
            mensagem = f"Idade válida: {idade} anos (mínimo: {idade_minima} anos)"
        else:
            # Calcular quando fará 15 anos
            data_nasc = datetime.strptime(data_nascimento, '%Y-%m-%d').date()
            hoje = date.today()
            
            # Data quando fará 15 anos
            data_15_anos = data_nasc.replace(year=data_nasc.year + idade_minima)
            
            # Calcular dias restantes
            dias_restantes = (data_15_anos - hoje).days
            
            if dias_restantes > 0:
                meses_restantes = dias_restantes // 30
                if meses_restantes > 0:
                    mensagem = f"Idade insuficiente: {idade} anos. Faltam {meses_restantes} meses para completar {idade_minima} anos"
                else:
                    mensagem = f"Idade insuficiente: {idade} anos. Faltam {dias_restantes} dias para completar {idade_minima} anos"
            else:
                mensagem = f"Idade insuficiente: {idade} anos (mínimo: {idade_minima} anos)"
        
        return jsonify({
            'success': True,
            'idade': idade,
            'idade_valida': idade_valida,
            'mensagem': mensagem,
            'data_nascimento': data_nascimento,
            'data_hoje': hoje.strftime('%d/%m/%Y'),
            'idade_minima': idade_minima
        })
        
    except Exception as e:
        print(f"✗ Erro ao verificar idade: {e}")
        return jsonify({
            'success': False,
            'message': f'Erro ao verificar idade: {str(e)}'
        }), 500

# ========== API DE CADASTRO COM VALIDAÇÃO DE IDADE ==========

@app.route('/api/cadastrar', methods=['POST'])
def cadastrar_usuario():
    """API para processar cadastro"""
    try:
        # Obter dados do formulário
        nome = request.form.get('nome', '').strip()
        telefone = request.form.get('telefone', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '').strip()
        data_nascimento = request.form.get('data_nascimento', '').strip()
        
        print(f"Dados recebidos: {nome}, {telefone}, {email}, {data_nascimento}")
        
        # Validação básica
        if not all([nome, telefone, email, senha, data_nascimento]):
            return jsonify({
                'success': False,
                'message': 'Todos os campos são obrigatórios!'
            }), 400
        
        # Validação específica
        if not validate_email(email):
            return jsonify({
                'success': False,
                'message': 'Formato de email inválido!'
            }), 400
        
        if not validate_date(data_nascimento):
            return jsonify({
                'success': False,
                'message': 'Data de nascimento inválida! Use o formato YYYY-MM-DD'
            }), 400
        
        # VALIDAÇÃO DE IDADE (15 ANOS OU MAIS)
        idade = calcular_idade(data_nascimento)
        if idade < 15:
            return jsonify({
                'success': False,
                'message': f'Não é possível cadastrar. Idade insuficiente: {idade} anos (mínimo: 15 anos)',
                'idade_atual': idade,
                'idade_minima': 15
            }), 400
        
        print(f"✓ Idade válida: {idade} anos")
        
        if len(senha) < 6:
            return jsonify({
                'success': False,
                'message': 'A senha deve ter no mínimo 6 caracteres!'
            }), 400
        
        # Conectar ao banco
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Erro de conexão com o banco de dados!'
            }), 500
        
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Verificar se email já existe
            cursor.execute("SELECT id FROM usuario WHERE email = %s", (email,))
            if cursor.fetchone():
                return jsonify({
                    'success': False,
                    'message': 'Este email já está cadastrado!'
                }), 400
            
            # Hash da senha
            senha_hash = hash_password(senha)
            print(f"Senha hash gerada: {senha_hash[:20]}...")
            
            # Inserir novo usuário (SEM idade no banco)
            insert_query = """
            INSERT INTO usuario (nome, telefone, email, senha, data_nascimento)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, nome, email
            """
            
            cursor.execute(insert_query, (nome, telefone, email, senha_hash, data_nascimento))
            user_id, user_nome, user_email = cursor.fetchone()
            conn.commit()
            
            print(f"Usuário cadastrado com ID: {user_id}")
            
            # Login automático após cadastro (opcional)
            session['user_id'] = user_id
            session['user_nome'] = user_nome
            session['user_email'] = user_email
            session['logged_in'] = True
            
            return jsonify({
                'success': True,
                'message': f'Cadastro realizado com sucesso!',
                'user': {
                    'id': user_id,
                    'nome': user_nome,
                    'email': user_email
                }
            })
            
        except Exception as e:
            print(f"✗ Erro durante cadastro: {e}")
            conn.rollback()
            return jsonify({
                'success': False,
                'message': f'Erro no cadastro: {str(e)}'
            }), 500
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                
    except Exception as e:
        print(f"✗ Erro inesperado no cadastro: {e}")
        return jsonify({
            'success': False,
            'message': 'Erro interno do servidor!'
        }), 500

# ========== API DE LOGIN ==========

@app.route('/api/login', methods=['POST'])
def login():
    """API para processar login"""
    try:
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '').strip()
        
        print(f"Tentativa de login - Email: {email}")
        
        # Validação básica
        if not email or not senha:
            return jsonify({
                'success': False,
                'message': 'Email e senha são obrigatórios!'
            }), 400
        
        # Conectar ao banco
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Erro de conexão com o servidor!'
            }), 500
        
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Buscar usuário
            print(f"Buscando usuário com email: {email}")
            
            cursor.execute("""
                SELECT id, nome, email, senha 
                FROM usuario 
                WHERE email = %s
            """, (email,))
            
            usuario = cursor.fetchone()
            
            if not usuario:
                print(f"Usuário não encontrado para email: {email}")
                return jsonify({
                    'success': False,
                    'message': 'Email não cadastrado!'
                }), 401
            
            user_id, nome, user_email, senha_hash = usuario
            print(f"Usuário encontrado: ID={user_id}, Nome={nome}")
            
            # Verificar senha
            senha_hash_calculada = hash_password(senha)
            if senha_hash != senha_hash_calculada:
                print("Senha incorreta!")
                return jsonify({
                    'success': False,
                    'message': 'Senha incorreta!'
                }), 401
            
            print(f"✓ Senha válida! Login autorizado para usuário {user_id}")
            
            # Atualizar último login
            try:
                cursor.execute("""
                    UPDATE usuario 
                    SET ultimo_login = CURRENT_TIMESTAMP 
                    WHERE id = %s
                """, (user_id,))
                conn.commit()
                print("Último login atualizado")
            except Exception as update_error:
                print(f"Aviso: Não foi possível atualizar último login: {update_error}")
                conn.rollback()
            
            # Criar sessão
            session['user_id'] = user_id
            session['user_nome'] = nome
            session['user_email'] = user_email
            session['logged_in'] = True
            
            print(f"Sessão criada: user_id={session['user_id']}")
            
            cursor.close()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Login realizado com sucesso!',
                'user': {
                    'id': user_id,
                    'nome': nome,
                    'email': user_email
                }
            })
            
        except Exception as e:
            print(f"✗ Erro durante login: {str(e)}")
            import traceback
            traceback.print_exc()
            
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                
            return jsonify({
                'success': False,
                'message': f'Erro interno: {str(e)}'
            }), 500
                
    except Exception as e:
        print(f"✗ Erro inesperado: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Erro interno do servidor!'
        }), 500

# ========== OUTRAS ROTAS ==========

@app.route('/api/logout', methods=['POST'])
def logout():
    """API para fazer logout"""
    session.clear()
    return jsonify({
        'success': True,
        'message': 'Logout realizado com sucesso!'
    })

@app.route('/api/check-session', methods=['GET'])
def check_session():
    """Verifica se usuário está logado"""
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

@app.route('/dashboard')
def dashboard():
    """Dashboard do usuário"""
    if 'user_id' not in session or not session.get('logged_in'):
        return redirect(url_for('login_page'))
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard</title>
    </head>
    <body>
        <h1>Bem-vindo, {session.get('user_nome')}!</h1>
        <p>Email: {session.get('user_email')}</p>
        <button onclick="logout()">Sair</button>
        <script>
            async function logout() {{
                await fetch('/api/logout', {{ method: 'POST' }});
                window.location.href = '/login';
            }}
        </script>
    </body>
    </html>
    """

@app.route('/usuarios')
def listar_usuarios():
    """Lista todos os usuários (para teste)"""
    conn = get_db_connection()
    if not conn:
        return "Erro de conexão", 500
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nome, telefone, email, 
                   data_nascimento, data_cadastro 
            FROM usuario
        """)
        usuarios = cursor.fetchall()
        
        html = "<h1>Usuários Cadastrados</h1><ul>"
        for u in usuarios:
            html += f"""
            <li>
                ID: {u[0]} | Nome: {u[1]} | Email: {u[3]}<br>
                Telefone: {u[2]} | Nasc: {u[4]} | Cadastro: {u[5]}
            </li>
            """
        html += "</ul><a href='/login'>Voltar</a>"
        
        cursor.close()
        conn.close()
        return html
        
    except Exception as e:
        print(f"Erro: {e}")
        return f"Erro: {e}", 500
    
    
   
    

# ========== INICIALIZAÇÃO ==========

if __name__ == '__main__':
    criar_tabela()
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.run(debug=True, port=5000)