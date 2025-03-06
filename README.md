# Introduction
 - This project is an inference deployment service for medical large models, aiming to provide a comprehensive, efficient, and intelligent solution for the medical industry. 
 - By integrating advanced LLM technologies, it has realized a series of core functions such as intelligent consultation, patient registration, patient profile establishment, diagnosis, examination order issuance, prescription, and treatment plan formulation. 
 - It is committed to improving the efficiency of medical services, enhancing the patient's medical experience, and promoting the intelligent development of the medical industry.

# Setup
## Environments setup
```bash
conda create -n seafarer_medical python=3.12
conda activate seafarer_medical
```

## Download
```bash
git clone -b develop https://github.com/MedFlow2025/medflow.git
```

## Reqirements setup
```bash
pip install -r requirements.txt
```

# Preparation: openai server
your openai server should be like this:
```bash
http://<ip>:<port>/v1 
```

# Preparation: proprietary data
Your medical library: diagnosis library, drug library, examination order library, etc. For examples, please refer to ./database.
```bash
python3 create_database.py
```

Your medical inspection rules.  For examples, please refer to quality/quality.json.

# Server run 
```bash
python3 inference.py --model <model_name> --model-url http://<openai ip>:<port>/v1 --fastbm25 --log --host <server ip> --port <server port> --max-round 30 --database ./database
```

# Test request
```bash
cd ./scripts

#对话生成患者建档
bash v1-jiandang.sh

#对话生成病历
bash v2-yuwenzhen.sh

#对话生成挂号
bash v3-guahao.sh

#生成诊断
bash v4-zhenduan.sh

#生成检查和化验
bash v5-jianchahuayan.sh

#生成多方案
bash v6-duofangan.sh
```

# Webui run
```bash
python3 inference_gradio.py --host <server ip> --port <server port> --gradio-port <webui port> --model <model_name>
```

# Contact Information
 - If you encounter problems during use or have any suggestions or ideas, please feel free to contact us in the following ways:

 - Github Issues: Submit issues on the Github page of this project, and we will reply and handle them in a timely manner.

 - We hope that this medical large model inference deployment service can bring new changes to the medical industry and provide better services for patients and medical workers. We look forward to your participation and support!
