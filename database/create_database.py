import os
import argparse
import openpyxl
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Double,
    Boolean,
    DateTime,
    insert,
    select,
    text,
)
import sqlalchemy

class DatabaseSchema:
    def __init__(self, name, excel_path, database_path):
        self.__remove__(name, database_path)
        self.engine = create_engine("sqlite:///"+database_path+"/"+name)
        self.excel_path = excel_path
        self.database_path = database_path
        self.metadata = MetaData()

    def __remove__(self, name, database_path):
        origin = os.path.join(database_path, name)
        if os.path.isfile(origin):
            os.remove(origin)
            print(f"Remove original file: {origin}")
        else:
            print(f"No original file: {origin}")

    def __create_table(self):
        department_info = Table(
            "department_info",
            self.metadata,
            Column('id', Integer, primary_key=True, nullable=False),
            Column('department_code', String, nullable=False),
            Column('department_hierarchy_code', String, nullable=False),
            Column('department_name', String, nullable=False),
            Column('alias', String),
            Column('remark', String)
        )
        diagnosis_info = Table(
            "diagnosis_info",
            self.metadata,
            Column('id', Integer, primary_key=True, nullable=False),
            Column('diagnosis_code', String, nullable=False),
            Column('diagnosis_name', String, nullable=False),
            Column('alias', String),
            Column('pinyin_shortcut_code', String),
            Column('country_diagnosis_code', String),
            Column('country_diagnosis_name', String),
            Column('remark', String)
        )
        examination_info = Table(
            'examination_info',
            self.metadata,
            Column('id', Integer, primary_key=True, nullable=False),
            Column('examination_code', String, nullable=False),
            Column('examination_name', String, nullable=False),
            Column('alias', String),
            Column('examination_category', String, nullable=False),
            Column('examination_subcategory', String),
            Column('remark', String)
        )
        laboratorytest_info = Table(
            'laboratorytest_info',
            self.metadata,
            Column('id', Integer, primary_key=True, nullable=False),
            Column('laboratorytest_catagory', String, nullable=False),
            Column('laboratorytest_code', String, nullable=False),
            Column('laboratorytest_name', String, nullable=False),
            Column('alias', String),
            Column('remark', String)
        )
        prescription_info = Table(
            'prescription_info',
            self.metadata,
            Column('id', Integer, primary_key=True, nullable=False),
            Column('drug_code', String, nullable=False),
            Column('drug_name', String, nullable=False),
            Column('alias', String),
            Column('drug_specification', String, nullable=False),
            Column('drug_category', String),
            Column('included_in_pharmacopoeia', String),
            Column('dosage_unit', String),
            Column('dosage', String),
            Column('pharmacy_unit', String),
            Column('drug_formulation', String),
            Column('country_drug_code', String),
            Column('country_drug_name', String),
            Column('remark', String)
        )
        transfusion_info = Table(
            'transfusion_info',
            self.metadata,
            Column('id', Integer, primary_key=True, nullable=False),
            Column('drug_code', String, nullable=False),
            Column('drug_name', String, nullable=False),
            Column('alias', String),
            Column('drug_specification', String, nullable=False),
            Column('drug_category', String),
            Column('included_in_pharmacopoeia', String),
            Column('dosage_unit', String),
            Column('dosage', String),
            Column('pharmacy_unit', String),
            Column('drug_formulation', String),
            Column('country_drug_code', String),
            Column('country_drug_name', String),
            Column('remark', String)
        )

        self.metadata.create_all(self.engine)

        self.table = {
            "department": department_info,
            "diagnosis": diagnosis_info,
            "examination": examination_info,
            "laboratorytest": laboratorytest_info,
            "prescription": prescription_info,
            "transfusion": transfusion_info
        }

    def __define_database(self):
        try:
            for root, dirs, files in os.walk(self.excel_path):
                break
            self.xlsx = dict((v.replace('.xlsx', ''), os.path.join(self.excel_path, v)) for v in files)
        except Exception as e:
            print(f"Error: please check weather the files in {self.excel_path} is correct.")
        else:
            for k, v in self.xlsx.items():
                #load data form excel
                content = openpyxl.load_workbook(v)
                sheet = content['Sheet1'] #Attention: Sheet1
                col_name = [c.key for c in self.table[k].c]
                data = []
                for index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if index != 0:
                        data.append(dict(zip(col_name, row)))

                #insert data to database table
                try:
                    for item in data:
                        stmt = insert(self.table[k]).values(**item)
                        with self.engine.begin() as connection:
                            cursor = connection.execute(stmt)
                    print(f"Table created successfully: {k}")
                except Exception as e:
                    print(f"Error inserting row into table: {self.table[k]}.")

    def __test_database(self):
        for k, v in self.table.items():
            stmt = select(*v.c.values()).select_from(v).where(v.c.id==1)
            with self.engine.connect() as connection:
                results = connection.execute(stmt).fetchall()
                print(f"TEST Table {k}: {results}")

    def extract_data(self):
        sql_str = dict((k, f"SELECT id, {str(v).replace('_info', '_name')}, alias from {str(v)}") 
            for k, v in self.table.items())
        exec_str = ""
        for k, v in sql_str.items():
            if k in ['prescription', 'transfusion']:
                exec_str = v.replace(k+'_name', 'drug_name')
            else:
                exec_str = v

            with self.engine.connect() as cn:
                try:
                    rows = cn.execute(text(exec_str)).fetchall()
                    print(f"Data extracted successfully: {k}")     
                except Exception as e:
                    print(f"Error executing query for {k}: {str(e)}")
                    continue

            try:
                with open(os.path.join(self.database_path, k, k+'.txt'), 'w') as f:
                    for r in rows:
                        f.write(f"{r[1] if r[2] is None else r[2]}\n")
                    print(f"Data written successfully: {k}")     
            except Exception as e:
                print(f"Error writing file {k}: {str(e)}")

    def run(self):
        self.__create_table()
        self.__define_database()
        self.__test_database()

def args_parser():
    parser = argparse.ArgumentParser(description='Database Schema for medical assistant.')
    parser.add_argument('--name', type=str, default='medical_assistant.db', help='Database name.')
    parser.add_argument('--excel-path', type=str, default='../excel', help='Path of excel.')
    parser.add_argument('--database-path', type=str, default='../database', help='Path of excel.')
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = args_parser()
    db = DatabaseSchema(args.name, args.excel_path, args.database_path)
    db.run()
    db.extract_data()
