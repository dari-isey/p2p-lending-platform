from database import create_tables, engine
from models import Base

if __name__ == "__main__":
    create_tables()
    print("Таблицы созданы")