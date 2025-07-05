import json
from app import app, db, Product  # Import the necessary objects from your main app

def create_database():
    """
    Creates the database tables if they don't already exist.
    """
    with app.app_context():
        db.create_all()
        print("Database tables created (if they didn't already exist).")

def migrate_products():
    """
    Reads products from products.json and adds any new ones to the database.
    """
    try:
        with open('products.json', 'r') as f:
            products_data = json.load(f)
    except FileNotFoundError:
        print("products.json not found. Skipping migration.")
        return

    with app.app_context():
        added_count = 0
        for p_data in products_data:
            # Check if a product with the same name already exists to avoid duplicates
            exists = Product.query.filter_by(name=p_data['name']).first()
            if not exists:
                new_product = Product(
                    name=p_data['name'],
                    description=p_data['description'],
                    price=p_data['price'],
                    image=p_data['image']
                )
                db.session.add(new_product)
                added_count += 1
        
        if added_count > 0:
            db.session.commit()
            print(f"Successfully added {added_count} new products to the database.")
        else:
            print("No new products to add. Database is already up-to-date.")

if __name__ == '__main__':
    print("--- Setting up the database ---")
    create_database()
    print("--- Migrating product data from JSON ---")
    migrate_products()
    print("--- Database setup complete! ---")