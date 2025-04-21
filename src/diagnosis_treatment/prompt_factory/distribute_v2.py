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

from ..prompt_template import *

@register_prompt
class PromptDistribute_v2(PromptTemplate):
    def __init__(self, receive) -> None:
        super().__init__()
        self.yaml_name = "distribute_v2.yaml"
        self.prompt_manager = PromptManager(self.yaml_name)

    def set_prompt(self):
        self.variables = {
            "format_distribute": self.format_distribute
        }
        self.prompt = {
            "0": self.__set_distribute()
        }
        return self.prompt

    def __set_distribute(self):
        system_str = self.prompt_manager.get_prompt("distribute", 0, self.variables)
        return system_str, None