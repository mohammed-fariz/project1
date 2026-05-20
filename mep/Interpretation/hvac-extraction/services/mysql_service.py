# import os
# import json
# import mysql.connector
# from dotenv import load_dotenv


# class MySQLService:
#     def __init__(self):
#         load_dotenv()

#         self.host = os.getenv("DB_HOST", "localhost")
#         self.port = int(os.getenv("DB_PORT", "3306"))
#         self.user = os.getenv("DB_USER", "root")
#         self.password = os.getenv("DB_PASSWORD")
#         self.database = os.getenv("DB_NAME", "hvac_db")

#     def _connect(self):
#             return mysql.connector.connect(
#                 host=self.host,
#                 port=self.port,
#                 user=self.user,
#                 password=self.password,
#                 database=self.database
#             )

#     def insert_extraction(self, filename: str, result: dict) -> int:
#         """
#         Stores the final extraction result JSON into MySQL.
#         Returns the inserted row ID.
#         """

#         query = """
#         INSERT INTO hvac_extraction (filename, project, result_json)
#         VALUES (%s, %s, %s)
#         """

#         project = result.get("project", "Unknown")
#         result_json = json.dumps(result, ensure_ascii=False)

#         connection = None
#         cursor = None

#         try:
#             connection = self._connect()
#             cursor = connection.cursor()

#             cursor.execute(query, (filename, project, result_json))
#             connection.commit()

#             return cursor.lastrowid

#         finally:
#             if cursor:
#                 cursor.close()
#             if connection:
#                 connection.close()

import os
import json
import mysql.connector

from dotenv import load_dotenv


class MySQLService:

    def __init__(self):

        load_dotenv()

        self.host = os.getenv("DB_HOST", "localhost")

        self.port = int(os.getenv("DB_PORT", "3306"))

        self.user = os.getenv("DB_USER", "root")

        self.password = os.getenv("DB_PASSWORD")

        self.database = os.getenv(

            "DB_NAME",
            "hvac_db"

        )

        # ======================================
        # AUTO CREATE DATABASE + TABLES
        # ======================================
        self._initialize_database()

    # ==========================================
    # MYSQL CONNECTION
    # ==========================================
    def _connect(self, use_database=True):

        connection_config = {

            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password

        }

        # CONNECT WITHOUT DATABASE
        if use_database:

            connection_config["database"] = self.database

        return mysql.connector.connect(

            **connection_config

        )

    # ==========================================
    # AUTO CREATE DATABASE + TABLES
    # ==========================================
    def _initialize_database(self):

        connection = None

        cursor = None

        try:

            # ==================================
            # CONNECT WITHOUT DB
            # ==================================
            connection = self._connect(

                use_database=False

            )

            cursor = connection.cursor()

            # ==================================
            # CREATE DATABASE
            # ==================================
            cursor.execute(

                f"""

                CREATE DATABASE IF NOT EXISTS
                {self.database}

                """

            )

            print(

                f"Database '{self.database}' ready"

            )

            cursor.close()

            connection.close()

            # ==================================
            # CONNECT TO DATABASE
            # ==================================
            connection = self._connect()

            cursor = connection.cursor()

            # ==================================
            # CREATE TABLE
            # ==================================
            create_table_query = """

            CREATE TABLE IF NOT EXISTS
            hvac_extraction (

                id INT PRIMARY KEY AUTO_INCREMENT,

                filename VARCHAR(255),

                project VARCHAR(255),

                result_json JSON,

                created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

            )

            """

            cursor.execute(

                create_table_query

            )

            connection.commit()

            print(

                "Table 'hvac_extraction' ready"

            )

        except Exception as e:

            print(

                "Database Initialization Error:"
            )

            print(e)

        finally:

            if cursor:

                cursor.close()

            if connection:

                connection.close()

    # ==========================================
    # INSERT EXTRACTION RESULT
    # ==========================================
    def insert_extraction(

        self,
        filename: str,
        result: dict

    ) -> int:

        query = """

        INSERT INTO hvac_extraction (

            filename,
            project,
            result_json

        )

        VALUES (%s, %s, %s)

        """

        project = result.get(

            "project",
            "Unknown"

        )

        result_json = json.dumps(

            result,
            ensure_ascii=False

        )

        connection = None

        cursor = None

        try:

            connection = self._connect()

            cursor = connection.cursor()

            cursor.execute(

                query,

                (

                    filename,
                    project,
                    result_json

                )

            )

            connection.commit()

            print("Extraction saved")

            return cursor.lastrowid

        except Exception as e:

            print("Insert Error:")
            print(e)

            return -1

        finally:

            if cursor:

                cursor.close()

            if connection:

                connection.close()