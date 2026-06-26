from flask import Flask, render_template, request, redirect, url_for, session, flash
from db import get_db_connection
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

# ---------- 辅助函数 ----------
def check_owner(table, id_column, record_id, user_id_column='user_id'):
    """检查当前用户是否拥有指定记录"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT {user_id_column} FROM {table} WHERE {id_column} = %s", (record_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return False, '记录不存在'
    if row[0] != session['user_id']:
        return False, '无权操作他人的数据'
    return True, None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """获取当前登录用户信息"""
    if 'user_id' in session:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, username, role FROM users WHERE user_id = %s", (session['user_id'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        return user
    return None

# ---------- 首页 ----------
@app.route('/')
def index():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    # 根据角色重定向到对应的功能页面
    if user['role'] == '种植户':
        return redirect(url_for('lands'))
    elif user['role'] == '采购商':
        return redirect(url_for('buyer'))
    elif user['role'] == '管理员':
        return redirect(url_for('admin_users'))
    return redirect(url_for('login'))

# ---------- 登录 / 注册 ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, username, role FROM users WHERE username = %s AND password = %s",
                    (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('登录成功')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', '种植户')
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, password, role)
            )
            conn.commit()
            flash('注册成功，请登录')
            return redirect(url_for('login'))
        except Exception:
            conn.rollback()
            flash('用户名已存在或注册失败')
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('已退出')
    return redirect(url_for('login'))

# ---------- 种植户功能：地块管理 ----------
@app.route('/lands', methods=['GET'])
@login_required
def lands():
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM lands WHERE user_id = %s ORDER BY land_id", (session['user_id'],))
    all_lands = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('lands.html', lands=all_lands)

@app.route('/lands/add', methods=['POST'])
@login_required
def add_land():
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    area = request.form.get('area')
    location = request.form.get('location')
    if not area or not location:
        flash('请填写完整信息')
        return redirect(url_for('lands'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO lands (area, location, user_id) VALUES (%s, %s, %s)",
                (area, location, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    flash('地块添加成功')
    return redirect(url_for('lands'))

@app.route('/lands/edit/<int:land_id>', methods=['POST'])
@login_required
def edit_land(land_id):
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    ok, err = check_owner('lands', 'land_id', land_id)
    if not ok:
        flash(err)
        return redirect(url_for('lands'))
    area = request.form.get('area')
    location = request.form.get('location')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE lands SET area=%s, location=%s WHERE land_id=%s", (area, location, land_id))
    conn.commit()
    cur.close()
    conn.close()
    flash('地块更新成功')
    return redirect(url_for('lands'))

@app.route('/lands/delete/<int:land_id>', methods=['POST'])
@login_required
def delete_land(land_id):
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    ok, err = check_owner('lands', 'land_id', land_id)
    if not ok:
        flash(err)
        return redirect(url_for('lands'))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 先删除该地块下所有果蔬关联的农事记录
        cur.execute("""
            DELETE FROM records WHERE fruit_id IN (
                SELECT fruit_id FROM fruits WHERE land_id = %s
            )
        """, (land_id,))
        # 删除该地块下所有果蔬关联的订单
        cur.execute("""
            DELETE FROM orders WHERE fruit_id IN (
                SELECT fruit_id FROM fruits WHERE land_id = %s
            )
        """, (land_id,))
        # 删除该地块下的所有果蔬
        cur.execute("DELETE FROM fruits WHERE land_id = %s", (land_id,))
        # 最后删除地块
        cur.execute("DELETE FROM lands WHERE land_id = %s", (land_id,))
        conn.commit()
        flash('地块已删除')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败：{str(e)}')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('lands'))

# ---------- 种植户功能：果蔬管理 ----------
@app.route('/fruits', methods=['GET'])
@login_required
def fruits():
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT f.*, l.location AS land_location
        FROM fruits f
        LEFT JOIN lands l ON f.land_id = l.land_id
        WHERE f.user_id = %s
        ORDER BY f.fruit_id
    """, (session['user_id'],))
    all_fruits = cur.fetchall()
    # 获取地块列表用于下拉选择（只看自己的地块）
    cur.execute("SELECT land_id, location FROM lands WHERE user_id = %s", (session['user_id'],))
    lands_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('fruits.html', fruits=all_fruits, lands=lands_list)

@app.route('/fruits/add', methods=['POST'])
@login_required
def add_fruit():
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    variety = request.form.get('variety')
    land_id = request.form.get('land_id')
    estimated_yield = request.form.get('estimated_yield')
    plant_time = request.form.get('plant_time') or None
    flower_time = request.form.get('flower_time') or None
    fruit_time = request.form.get('fruit_time') or None
    maturity = request.form.get('maturity', '生长期')
    if not variety or not land_id or not estimated_yield:
        flash('请填写完整信息')
        return redirect(url_for('fruits'))
    # 验证地块属于当前用户
    ok, err = check_owner('lands', 'land_id', land_id)
    if not ok:
        flash(err)
        return redirect(url_for('fruits'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO fruits (variety, plant_time, flower_time, fruit_time, maturity, estimated_yield, purchased_yield, land_id, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (variety, plant_time, flower_time, fruit_time, maturity, estimated_yield, 0, land_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    flash('果蔬批次添加成功')
    return redirect(url_for('fruits'))

@app.route('/fruits/edit/<int:fruit_id>', methods=['POST'])
@login_required
def edit_fruit(fruit_id):
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    ok, err = check_owner('fruits', 'fruit_id', fruit_id)
    if not ok:
        flash(err)
        return redirect(url_for('fruits'))
    variety = request.form.get('variety')
    land_id = request.form.get('land_id')
    estimated_yield = request.form.get('estimated_yield')
    purchased_yield = request.form.get('purchased_yield', 0)
    plant_time = request.form.get('plant_time') or None
    flower_time = request.form.get('flower_time') or None
    fruit_time = request.form.get('fruit_time') or None
    maturity = request.form.get('maturity')
    # 验证新地块也属于当前用户
    ok, err = check_owner('lands', 'land_id', land_id)
    if not ok:
        flash('地块' + err)
        return redirect(url_for('fruits'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE fruits SET
            variety=%s, land_id=%s, estimated_yield=%s, purchased_yield=%s,
            plant_time=%s, flower_time=%s, fruit_time=%s, maturity=%s
        WHERE fruit_id=%s
    """, (variety, land_id, estimated_yield, purchased_yield, plant_time, flower_time, fruit_time, maturity, fruit_id))
    conn.commit()
    cur.close()
    conn.close()
    flash('果蔬更新成功')
    return redirect(url_for('fruits'))

@app.route('/fruits/delete/<int:fruit_id>', methods=['POST'])
@login_required
def delete_fruit(fruit_id):
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    ok, err = check_owner('fruits', 'fruit_id', fruit_id)
    if not ok:
        flash(err)
        return redirect(url_for('fruits'))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 先删除关联的农事记录和订单
        cur.execute("DELETE FROM records WHERE fruit_id = %s", (fruit_id,))
        cur.execute("DELETE FROM orders WHERE fruit_id = %s", (fruit_id,))
        # 再删除果蔬
        cur.execute("DELETE FROM fruits WHERE fruit_id=%s", (fruit_id,))
        conn.commit()
        flash('已删除')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败：{str(e)}')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('fruits'))

# ---------- 种植户功能：农事记录 ----------
@app.route('/records', methods=['GET'])
@login_required
def records():
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    fruit_id_filter = request.args.get('fruit_id')
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if fruit_id_filter:
        cur.execute("""
            SELECT r.*, f.variety AS fruit_variety
            FROM records r
            LEFT JOIN fruits f ON r.fruit_id = f.fruit_id
            WHERE r.fruit_id = %s AND f.user_id = %s
            ORDER BY r.record_id
        """, (fruit_id_filter, session['user_id']))
    else:
        cur.execute("""
            SELECT r.*, f.variety AS fruit_variety
            FROM records r
            LEFT JOIN fruits f ON r.fruit_id = f.fruit_id
            WHERE f.user_id = %s
            ORDER BY r.record_id
        """, (session['user_id'],))
    all_records = cur.fetchall()
    # 获取自己的果蔬列表用于过滤
    cur.execute("SELECT fruit_id, variety FROM fruits WHERE user_id = %s", (session['user_id'],))
    fruits_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('records.html', records=all_records, fruits=fruits_list, selected_fruit=fruit_id_filter)

@app.route('/records/add', methods=['POST'])
@login_required
def add_record():
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    fruit_id = request.form.get('fruit_id')
    operation_type = request.form.get('operation_type')
    operation_time = request.form.get('operation_time')
    details = request.form.get('details')
    if not fruit_id or not operation_type or not operation_time:
        flash('请填写完整信息')
        return redirect(url_for('records'))
    # 验证果蔬属于当前用户
    ok, err = check_owner('fruits', 'fruit_id', fruit_id)
    if not ok:
        flash(err)
        return redirect(url_for('records'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO records (operation_type, operation_time, details, fruit_id)
        VALUES (%s, %s, %s, %s)
    """, (operation_type, operation_time, details, fruit_id))
    conn.commit()
    cur.close()
    conn.close()
    flash('农事记录添加成功')
    return redirect(url_for('records'))

@app.route('/records/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    if session['role'] != '种植户':
        flash('权限不足')
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor()
    # 验证记录关联的果蔬属于当前用户
    cur.execute("""
        SELECT f.user_id FROM records r
        JOIN fruits f ON r.fruit_id = f.fruit_id
        WHERE r.record_id = %s
    """, (record_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        flash('记录不存在')
        return redirect(url_for('records'))
    if row[0] != session['user_id']:
        cur.close()
        conn.close()
        flash('无权操作他人的数据')
        return redirect(url_for('records'))
    cur.execute("DELETE FROM records WHERE record_id=%s", (record_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('记录已删除')
    return redirect(url_for('records'))

# ---------- 采购商功能 ----------
@app.route('/buyer')
@login_required
def buyer():
    if session['role'] != '采购商':
        flash('权限不足')
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # 获取所有成熟可售的果蔬
    cur.execute("""
        SELECT f.*, l.location AS land_location 
        FROM fruits f
        LEFT JOIN lands l ON f.land_id = l.land_id
        WHERE f.maturity = '成熟可售'
    """)
    mature_fruits = cur.fetchall()
    # 获取当前采购商的订单
    cur.execute("""
        SELECT o.*, f.variety AS fruit_variety
        FROM orders o
        LEFT JOIN fruits f ON o.fruit_id = f.fruit_id
        WHERE o.user_id = %s
        ORDER BY o.order_id DESC
    """, (session['user_id'],))
    my_orders = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('buyer.html', fruits=mature_fruits, orders=my_orders)

@app.route('/purchase', methods=['POST'])
@login_required
def purchase():
    if session['role'] != '采购商':
        flash('权限不足')
        return redirect(url_for('index'))
    fruit_id = request.form.get('fruit_id')
    amount = request.form.get('amount')
    price = request.form.get('price')
    if not fruit_id or not amount or not price:
        flash('请填写完整信息')
        return redirect(url_for('buyer'))
    try:
        amount = float(amount)
        price = float(price)
    except ValueError:
        flash('数量或单价格式错误')
        return redirect(url_for('buyer'))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO orders (amount, price, user_id, fruit_id) VALUES (%s, %s, %s, %s)",
            (amount, price, session['user_id'], fruit_id)
        )
        conn.commit()
        flash('采购成功！')
    except Exception as e:
        conn.rollback()
        flash(f'采购失败：{str(e)}')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('buyer'))

# ---------- 管理员功能 ----------
@app.route('/admin/users')
@login_required
def admin_users():
    if session['role'] != '管理员':
        flash('权限不足')
        return redirect(url_for('index'))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id, username, role FROM users ORDER BY user_id")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if session['role'] != '管理员':
        flash('权限不足')
        return redirect(url_for('index'))
    if user_id == session['user_id']:
        flash('不能删除自己')
        return redirect(url_for('admin_users'))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 删除该用户果蔬关联的农事记录
        cur.execute("""
            DELETE FROM records WHERE fruit_id IN (
                SELECT fruit_id FROM fruits WHERE user_id = %s
            )
        """, (user_id,))
        # 删除该用户的订单和该用户果蔬的订单
        cur.execute("""
            DELETE FROM orders WHERE user_id = %s OR fruit_id IN (
                SELECT fruit_id FROM fruits WHERE user_id = %s
            )
        """, (user_id, user_id))
        # 删除该用户的果蔬
        cur.execute("DELETE FROM fruits WHERE user_id = %s", (user_id,))
        # 最后删除用户
        cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
        conn.commit()
        flash('用户已删除')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败：{str(e)}')
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    app.run(debug=True)