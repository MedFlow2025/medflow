# Copyright (c) 2025,  IEIT SYSTEMS Co.,Ltd.  All rights reserved

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from fastbm25 import fastbm25
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import time

def fastbm25_engine(database_url):
    # Loading Best Matching 25 ranking doucuments
    bm25_engine = {}
    try:
        for root, dirs, file in os.walk(database_url):
            break
        input_dir = [os.path.join(database_url, v, v + ".txt") for v in dirs if v != "quality"]
    except Exception as e:
        print(f"Error: please check weather the files in {database_url} is correct.")
    else:
        for i, j in enumerate(input_dir):
            corpus = []
            with open(j, "r") as f:
                lines = f.readlines()
                for line in lines:
                    corpus.append(line.strip())
            bm25_engine[os.path.splitext(os.path.basename(j))[0]] = fastbm25(corpus)
    return bm25_engine


def search_database(engine, sql_str:str, max_retries=3, retry_delay=1):
    # Search data from database
    search_result = []
    retries = 0
    while retries < max_retries:
        try:
            with engine.connect() as con:
                rows = con.execute(text(sql_str))
                for row in rows:
                    search_result.append(row)
                break  # 如果执行成功，跳出重试循环
        except SQLAlchemyError as e:
            print(f"Error: sql statement error.  Details: {str(e)} ")
            retries += 1
            if retries < max_retries:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)  # 等待一段时间后重试
    return search_result  

def character_percentage(sen_q, sen_r):
    set_q, set_r =  set(sen_q), set(sen_r)
    common_characters = set_q.intersection(set_r)
    common_count, q_count = len(common_characters), len(set_q)
    percentage = (common_count / q_count)  if common_count > 0 else 0

    if q_count >= 4 and percentage >= 0.75:
        return True
    elif q_count <= 3 and percentage == 1:
        return True
    else:
        return False

def query_fastbm25(database_url, query_item: str, engine_flag: str):
    # Using bm25, return rank
    bm25_engine = fastbm25_engine(database_url)
    model = bm25_engine.get(engine_flag)
    results = model.top_k_sentence(query_item, k=10)
    flag = False
    if results != []:
        flag = character_percentage(query_item, results[0][0])
    return results if flag else None