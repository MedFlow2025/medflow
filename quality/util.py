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

def handle_quality(quality_path):
    with open(quality_path, 'r') as f:
        input = f.read()
    qs = json.loads(input)
    quality_settings = qs['check_quality']
    return quality_settings 

def check_and_create_path(path):
    if not os.path.exists(path):
        os.makedirs(path)
