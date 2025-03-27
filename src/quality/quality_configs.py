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
import json
import re
import threading
from .util import handle_quality, check_and_create_path

DEFAULT_CONFIG_FILE_NAME = "quality_default"

class QualityConfigs:
    def __init__(self,
                 base_config_file : str,
    ):
        self.base_config_file = base_config_file
        self.lock = threading.Lock()
        parent_dir = os.path.dirname(base_config_file)
        self.configs_path = parent_dir
        self.quality_configs = {}
        self.default_config_settings = handle_quality(self.base_config_file)
        self.quality_configs[DEFAULT_CONFIG_FILE_NAME] = self.default_config_settings
        self.check_all_quality_configs()

    def check_all_quality_configs(self):
        check_and_create_path(self.configs_path)
        for root, dirs, files in os.walk(self.configs_path):
            for file in files:
                if file.startswith("quality_") and file.endswith(".json"):
                    file_name_without_extension = os.path.splitext(file)[0] 
                    file_path = os.path.join(root, file)
                    try:
                        with self.lock:
                            self.quality_configs[file_name_without_extension] = handle_quality(file_path)
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")        


    def get_quality_config_by_name(self, config_name : str):
        ret_config = self.quality_configs.get(config_name)
        return ret_config
    
    def get_default_quality_config(self):
        return self.default_config_settings
