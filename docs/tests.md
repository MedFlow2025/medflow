## 脚本说明

| 功能       | 测试脚本                                                     | 说明                                                         | 是否对话 |
| ---------- | ------------------------------------------------------------ | ------------------------------------------------------------ | -------- |
| 患者建档   | [test-clientinfo.sh](../tests/test-clientinfo.sh)            | 收集患者的姓名、证件号码、联系方式等，生成建档信息，带有基础的校验功能。 | Y        |
| 导诊       | [test-hospitalguide.sh](../tests/test-hospitalguide.s)       | 简单了解患者的病情，并为患者指引科室。                       | Y        |
| 预问诊报告 | [test-basicmedicalrecord.sh](../tests/test-basicmedicalrecord.sh) | 收集患者的主诉、现病史、既往史、个人史、过敏史等，生成预问诊报告。 | Y        |
| 挂号       | [test-register.sh](../tests/test-register.sh)                | 理解患者的意图，为患者推荐合适的挂号信息。                   | Y        |
| 诊断       | [test-diagnosis.sh](../tests/test-diagnosis.sh)              | 根据预问诊报告，生成初步诊断结果。                           | N        |
| 检查和化验 | [test-examineassay.sh](../tests/test-examineassay.sh)        | 根据预问诊报告和诊断结果，生成检查单和化验单。               | N        |
| 治疗方案   | [test-therapyscheme.sh](../tests/test-therapyscheme.sh)      | 根据预问诊报告和诊断结果，生成治疗方案。                     | N        |
| 复诊       | [test-returnvisit.sh](../tests/test-returnvisit.sh)          | 根据上次就诊记录，向患者了解治疗效果，判断是否需要复诊。     | Y        |
| 病历       | [test-doctormedicalrecord.sh](../tests/test-doctormedicalrecord.sh) | 根据医生的描述，AI对病历进行修改，支持普通病历与模板病历的修改。 | N        |

