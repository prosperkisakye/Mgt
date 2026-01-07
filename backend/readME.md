# SUPAMAX

## Overview
This is a Django-based Organisation Management System designed to handle various operations such as product management, sales tracking, and inventory control. The project follows best practices by utilizing a virtual environment, environment variables, and code formatting with Black.

## Setup Instructions

### Prerequisites
Ensure you have the following installed:
- Python 3.10 or greater
- Virtualenv (optional but recommended)

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/BAIFAM/SUPAMAX.git
   cd SUPAMAX
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install GDAL:**
   - Install GDAL and its development libraries
      ```
      sudo apt install -y gdal-bin libgdal-dev
      ```
5. **Enable postgis In PostgresDB:**
   - To run this command, it requires a superuser logged and connected to the DB
   ```
   sudo apt install postgresql-16-postgis-3
   sudo systemctl restart postgresql
   ```

   ```
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

   - To confirm, use command "\dx"

6. **Enable PgVector In PostgresDB:**

   - To run this command, it requires a superuser logged and connected to the DB

   ```
   chmod +x setup_pgvector.sh
   ./setup_pgvector.sh

   ```


6. **Set up environment variables:**
   - Copy `.env-example` to `.env` and update the values accordingly.
   ```bash
   cp .env-example .env
   ```

7. **Apply migrations:**
   ```bash
   python manage.py migrate
   ```

9. **Run Load the DB Schema Embedding:**

   ```bash
   python manage.py load_schema_embeddings
   ```

10. **Run the development server:**
   ```bash
   daphne core.asgi:application
   ```

11. **Celery commands**
   ```bash
   celery -A core worker -l info


   ```bash
   celery -A core beat -l info
   ```
## Code Formatting
This project uses [Black](https://black.readthedocs.io/en/stable/) for code formatting.

## Database Design
Refer to the [ERD](https://drive.google.com/file/d/1u8sCGMIVE-ZJ0ZLSvlWwotukZq1LdGjc/view?usp=sharing) for database structure details.

## Redis
The project uses [redis](https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-on-linux/)

## Features
- Product Management
- Inventory Tracking
- Sales Processing
- Customer Management
- Reports & Analytics

## to generate a field encryption key
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"


## install latexmk
sudo apt-get install texlive-latex-extra texlive-fonts-recommended latexmk