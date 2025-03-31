from flask import Flask, render_template, request, redirect, url_for, flash, current_app
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from werkzeug.security import generate_password_hash, check_password_hash
from config import config
from utils.cosmos_db import create_item, get_item, query_items, update_item, delete_item
import os
from werkzeug.utils import secure_filename
import uuid

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # Initialize rate limiter
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    
    # Initialize security headers
    Talisman(app, 
        content_security_policy={
            'default-src': "'self'",
            'img-src': "'self' data: https:",
            'script-src': "'self' 'unsafe-inline' 'unsafe-eval' https:",
            'style-src': "'self' 'unsafe-inline' https:",
            'font-src': "'self' https: data:",
        }
    )
    
    # User class for Flask-Login
    class User(UserMixin):
        def __init__(self, user_data):
            self.id = user_data['id']
            self.username = user_data['username']
            self.email = user_data['email']
            self.password_hash = user_data['password_hash']
            self.cart_items = user_data.get('cart_items', [])

        @staticmethod
        def get(user_id):
            user_data = get_item('users', user_id, user_id)
            if user_data:
                return User(user_data)
            return None

        def set_password(self, password):
            self.password_hash = generate_password_hash(password)

        def check_password(self, password):
            return check_password_hash(self.password_hash, password)

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    # Routes
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit("5 per minute")
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Query users container for the username
            users = query_items('users', 
                "SELECT * FROM c WHERE c.username = @username",
                [{"name": "@username", "value": username}]
            )
            
            if users and users[0]:
                user = User(users[0])
                if user.check_password(password):
                    login_user(user)
                    return redirect(url_for('products'))
            flash('Invalid username or password')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    @limiter.limit("3 per minute")
    def register():
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            
            # Check if username exists
            existing_users = query_items('users',
                "SELECT * FROM c WHERE c.username = @username",
                [{"name": "@username", "value": username}]
            )
            
            if existing_users:
                flash('Username already exists')
                return redirect(url_for('register'))
            
            # Create new user
            user = User({
                'id': username,  # Using username as ID for simplicity
                'username': username,
                'email': email,
                'password_hash': generate_password_hash(password),
                'cart_items': []
            })
            
            create_item('users', user.__dict__)
            return redirect(url_for('login'))
        return render_template('register.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/products')
    @login_required
    def products():
        search_query = request.args.get('search', '')
        category = request.args.get('category', '')
        
        # Query products
        query = "SELECT * FROM c"
        parameters = []
        
        if search_query:
            query += " WHERE c.name LIKE @search"
            parameters.append({"name": "@search", "value": f"%{search_query}%"})
        if category:
            query += " AND c.category = @category" if search_query else " WHERE c.category = @category"
            parameters.append({"name": "@category", "value": category})
            
        products = query_items('products', query, parameters)
        categories = query_items('products', "SELECT DISTINCT VALUE c.category FROM c")
        return render_template('products.html', products=products, categories=categories)

    @app.route('/add_to_cart/<product_id>')
    @login_required
    def add_to_cart(product_id):
        # Get product
        product = get_item('products', product_id, product_id)
        if not product:
            flash('Product not found')
            return redirect(url_for('products'))
        
        # Get user's cart
        user = User.get(current_user.id)
        cart_items = user.cart_items
        
        # Update cart
        cart_item = next((item for item in cart_items if item['product_id'] == product_id), None)
        if cart_item:
            cart_item['quantity'] += 1
        else:
            cart_items.append({
                'product_id': product_id,
                'quantity': 1
            })
        
        # Update user in database
        user.cart_items = cart_items
        update_item('users', user.id, user.id, user.__dict__)
        
        flash('Product added to cart')
        return redirect(url_for('products'))

    @app.route('/cart')
    @login_required
    def cart():
        user = User.get(current_user.id)
        cart_items = []
        total = 0
        
        for item in user.cart_items:
            product = get_item('products', item['product_id'], item['product_id'])
            if product:
                cart_items.append({
                    'product': product,
                    'quantity': item['quantity']
                })
                total += product['price'] * item['quantity']
        
        return render_template('cart.html', cart_items=cart_items, total=total)

    @app.route('/account')
    @login_required
    def account():
        return render_template('account.html', user=current_user)

    # Admin routes
    @app.route('/admin')
    @login_required
    def admin():
        # Get all products
        products = query_items('products', "SELECT * FROM c")
        return render_template('admin.html', products=products)

    @app.route('/admin', methods=['POST'])
    @login_required
    def add_product():
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        category = request.form.get('category')
        
        # Generate unique ID
        product_id = str(uuid.uuid4())
        
        # Handle image upload
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Upload to Azure Storage (you'll need to implement this)
                # image_url = upload_to_azure_storage(file)
        
        # Create product
        product = {
            'id': product_id,
            'name': name,
            'description': description,
            'price': price,
            'category': category,
            'image_url': image_url
        }
        
        create_item('products', product)
        flash('Product added successfully')
        return redirect(url_for('admin'))

    @app.route('/admin/product/<product_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_product(product_id):
        if request.method == 'POST':
            product = get_item('products', product_id, product_id)
            if product:
                product['name'] = request.form.get('name')
                product['description'] = request.form.get('description')
                product['price'] = float(request.form.get('price'))
                product['category'] = request.form.get('category')
                
                # Handle image upload
                if 'image' in request.files:
                    file = request.files['image']
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        # Upload to Azure Storage (you'll need to implement this)
                        # product['image_url'] = upload_to_azure_storage(file)
                
                update_item('products', product_id, product_id, product)
                flash('Product updated successfully')
                return redirect(url_for('admin'))
        
        product = get_item('products', product_id, product_id)
        return render_template('edit_product.html', product=product)

    @app.route('/admin/product/<product_id>/delete', methods=['POST'])
    @login_required
    def delete_product(product_id):
        delete_item('products', product_id, product_id)
        flash('Product deleted successfully')
        return redirect(url_for('admin'))

    def allowed_file(filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('500.html'), 500

    return app

app = create_app(os.getenv('FLASK_ENV', 'default'))

if __name__ == '__main__':
    # Initialize sample products if needed
    products = query_items('products', "SELECT * FROM c")
    if not products:
        sample_products = [
            {
                'id': 'laptop',
                'name': 'Laptop',
                'description': 'High-performance laptop',
                'price': 999.99,
                'category': 'Electronics'
            },
            {
                'id': 'smartphone',
                'name': 'Smartphone',
                'description': 'Latest smartphone',
                'price': 699.99,
                'category': 'Electronics'
            },
            {
                'id': 'headphones',
                'name': 'Headphones',
                'description': 'Wireless headphones',
                'price': 199.99,
                'category': 'Accessories'
            },
            {
                'id': 'smartwatch',
                'name': 'Smartwatch',
                'description': 'Fitness smartwatch',
                'price': 299.99,
                'category': 'Accessories'
            }
        ]
        for product in sample_products:
            create_item('products', product)
    
    app.run(debug=app.config['DEBUG']) 