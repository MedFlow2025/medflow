import yaml

_config = {}

import os
import yaml

# 全局配置字典
_config = {}
PROMPT_YAMLS_ROOT_DIR = "../data/raw/prompt"

def load_config(root_dir = PROMPT_YAMLS_ROOT_DIR):
    global _config
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.yaml'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        yaml_data = yaml.safe_load(f)
                        if yaml_data is not None:
                            for key, value in yaml_data.items():
                                if key in _config:
                                    if isinstance(_config[key], dict) and isinstance(value, dict):
                                        # 递归合并嵌套字典
                                        _config[key] = _recursive_merge(_config[key], value)
                                    else:
                                        _config[key] = value
                                else:
                                    _config[key] = value
                except FileNotFoundError:
                    print(f"配置文件 {file_path} 未找到")
                except yaml.YAMLError as e:
                    print(f"解析 YAML 文件 {file_path} 时出错: {e}")

def _recursive_merge(dict1, dict2):
    """
    递归合并两个字典
    """
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _recursive_merge(result[key], value)
        else:
            result[key] = value
    return result

def get_config():
    return _config

# 在模块被导入时加载配置
load_config()