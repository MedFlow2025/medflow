import openai
import pandas as pd
from openai import OpenAI
import numpy as np
import time

# 全局变量
xlsx_file = None
client = None



def assess_symptom_complexity(chief_complaint: str) -> int:
    """
    使用大模型判断症状复杂度
    返回：1-简单 2-中等 3-复杂
    """
    global client
    prompt = f"""作为急诊科主任医师，请评估以下主诉的复杂度：
    
【主诉内容】
{chief_complaint}

【复杂度标准】
1级（简单）：单一系统、轻微症状（如感冒、皮疹）
2级（中等）：多系统症状或中度不适（如腹痛伴呕吐）
3级（复杂）：危重症状或潜在生命危险（如胸痛、意识障碍）

请直接返回数字1/2/3，不要包含任何其他内容"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=2
        )
        print(f"病历:\n{chief_complaint}")        
        print(f"复杂度为: {response.choices[0].message.content}")
        complexity = int(response.choices[0].message.content.strip())
        return max(1, min(3, complexity))  # 确保在1-3范围内
    except:
        return 2  # 默认中等复杂度

def evaluate_agent_response(full_conversation: str, agent_response: str, 
                          round_num: int, symptom_complexity: int) -> tuple:
    """整合复杂度评估的问诊质量评估"""
    
    # 获取当前轮次的基准要求
    round_benchmarks = {
        1: (5, 4),   # (建议信息点, 最低要求)
        2: (7, 4),
        3: (9, 4)
    }[symptom_complexity]
    
    prompt = f"""
【临床问诊质量评估】
主诉复杂度：{symptom_complexity}级（{'简单/中等/复杂'[symptom_complexity-1]}）
当前轮次：第{round_num}轮

【对话上下文】
{full_conversation}

【待评估回复】
{agent_response}

请从以下维度评分：
1. 临床信息收集（50分）
- 症状特征（15分）
- 病因排查（15分） 
- 病史采集（20分）

2. 沟通技巧（30分）
- 问诊逻辑（20分）
- 患者互动（10分）

3. 诊断质量（20分）
- 初步推断（10分）
- 鉴别诊断（10分）

需严格注意：当医生回复出现以下任一情况时，三方面评分均为0分：
    1.复述患者提过的信息
    2.在对话中提到总结主诉、现病史等病历信息
    3.重复提问对话上下文中问过的问题
评分格式（逗号分隔）：
临床得分,沟通得分,诊断得分"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": prompt}],
            temperature=1.0,
            max_tokens=100
        )
        print(f"完整对话上下文:\n{full_conversation}")
        print(f"医生回复:\n{agent_response}")
        print(f"得分为: {response.choices[0].message.content}")
        scores = list(map(float, response.choices[0].message.content.split('\n')[0].strip().split(',')))
        
        return tuple(scores + [symptom_complexity])  # 追加复杂度信息
        
    except Exception as e:
        print(f"评估出错: {e}")
        return (0, 0, 0, symptom_complexity)

def build_conversation_context(df: pd.DataFrame, current_index: int) -> str:
    """
    构建对话上下文，包含当前轮次前的所有对话内容
    新增功能：
    1. 检测吸烟史相关询问并提前终止
    2. 更精细的对话历史管理
    3. 支持Role和Agent_Role双列格式
    """
    full_conversation_history = []
    
    # 从第二行开始（假设第一行是主诉），跳过最后5行
    for i in range(1, min(current_index + 1, len(df) - 5)):
        row = df.iloc[i]
        role = row['Role']
        content = row['Content']
        agent_role = row['Agent_Role']
        agent_content = row['Agent_Content']
        
        # 吸烟史检测
        if any(keyword in agent_content for keyword in ["吸烟", "抽烟", "吸烟史"]):
            print(f"检测到吸烟史询问，终止评估: {agent_content}")
            break
            
        # 构建对话历史
        full_conversation_history.append(f"{role}: {content}")
        if agent_role and agent_content:  # 确保有agent内容
            full_conversation_history.append(f"{agent_role}: {agent_content}")
    
    return "\n".join(full_conversation_history)

def process_sheet(sheet_name: str) -> dict:
    """处理单个工作表，整合新的上下文构建方式"""
    df = pd.read_excel(xlsx_file, sheet_name=sheet_name)
    
    # 自动判断症状复杂度（使用第一行的Content作为主诉）
    first_content = df.iloc[0]['Content']
    complexity = assess_symptom_complexity(first_content)
    time.sleep(1)
    
    round_scores = []
    full_conversation_history = []
    round_benchmarks = {1: 4, 2: 4, 3: 4}[complexity] 
    round_suggestion = {1: 5, 2: 7, 3: 9}[complexity] 
    
    for i in range(1, len(df) - 5):  # 跳过第一行主诉和最后5行
        row = df.iloc[i]
        
        # 吸烟史检测
        if any(keyword in str(row['Agent_Content']).lower() for keyword in ["吸烟", "抽烟", "吸烟史"]):
            print(f"检测到吸烟史询问，终止评估: {row['Agent_Content']}")
            break
            
        # 构建完整对话历史（包括当前轮次）
        current_dialog = f"{row['Role']}: {row['Content']}\n{row['Agent_Role']}: {row['Agent_Content']}"
        full_conversation = "\n".join(full_conversation_history + [f"{row['Role']}: {row['Content']}"])
        
        # 只评估agent的回复
        if row['Agent_Role'] == "assistant":
            evaluation = evaluate_agent_response(
                full_conversation=full_conversation,
                agent_response=f"{row['Agent_Role']}: {row['Agent_Content']}",
                round_num=len(round_scores)+1,
                symptom_complexity=complexity
            )
            round_scores.append(evaluation)
        
        # 更新对话历史
        full_conversation_history.append(f"{row['Role']}: {row['Content']}")
        full_conversation_history.append(f"{row['Agent_Role']}: {row['Agent_Content']}")
        time.sleep(0.5)
    
    # 计算得分
    avg_basic_score = np.mean([sum(s[:3]) for s in round_scores]) if round_scores else 0
    
    # 更精细的轮次达标判断
    if len(round_scores) < round_benchmarks:
        meets_round_requirement = 0
        print(f"警告: 当前对话轮次({len(round_scores)})低于最低要求({round_benchmarks})")
    elif round_suggestion > len(round_scores) >= round_benchmarks:
        meets_round_requirement = 50
        print(f"达标: 当前对话轮次({len(round_scores)})达到最低要求({round_benchmarks})")
    else:
        meets_round_requirement = 100
        print(f"优秀: 当前对话轮次({len(round_scores)})超过建议值({round_suggestion})")
    
    weighted_score = avg_basic_score * 0.8 + meets_round_requirement * 0.2
    
    return {
        "sheet_name": sheet_name,
        "complexity": complexity,
        "avg_score": avg_basic_score,
        "avg_weighted_score": weighted_score,
        "rounds": len(round_scores),
        "meets_round_requirement": meets_round_requirement,
        "detail": round_scores
    }
# 主程序
if __name__ == "__main__":
    import argparse
    def main():
        global client, xlsx_file 
        
        # 创建参数解析器
        parser = argparse.ArgumentParser(description='临床问诊质量评估工具')
        
        # 添加参数定义
        parser.add_argument('--input', type=str, required=True,
                          help='需要打分的对话Excel文件路径（必填）')
        parser.add_argument('--api_key', type=str, required=True,
                          help='API密钥（必填）')
        parser.add_argument('--url', type=str, default="https://api.deepseek.com/v1",
                          help='API基础URL（默认为DeepSeek官方API）')
        parser.add_argument('--model', type=str, default="deepseek-chat",
                          help='使用的模型名称（默认为deepseek-chat）')
        parser.add_argument('--start_sheet', type=int, default=1,
                          help='起始工作表索引（默认为1）')
        parser.add_argument('--end_sheet', type=int, default=85,
                          help='结束工作表索引（默认为85）')
        
        # 解析参数
        args = parser.parse_args()
        
        # 初始化OpenAI客户端（移动到main函数内）
        client = OpenAI(api_key=args.api_key, base_url=args.url)
        
        global xlsx_file
        xlsx_file = args.input
        results = []
        
        # 获取所有工作表名，排除可能的非数据表
        sheet_names = [name for name in pd.ExcelFile(xlsx_file).sheet_names 
                      if not name.startswith('_')]  # 跳过可能的工作表
        
        for sheet in sheet_names[args.start_sheet:args.end_sheet]:  # 使用参数控制范围
            print(f"\n{'='*40}\n正在分析：{sheet}\n{'='*40}")
            try:
                result = process_sheet(sheet)
                results.append(result)
                # 打印当前工作表的平均分
                print(f"\n工作表 '{sheet}' 分析完成 - 平均分: {result['avg_score']:.2f} 分")
                time.sleep(2)  # 控制请求频率
            except Exception as e:
                print(f"处理工作表 {sheet} 时出错: {e}")
                continue
        
        if not results:
            print("\n没有可分析的工作表数据")
        else:
            # 生成分级报告
            report = pd.DataFrame([{
                "工作表": r["sheet_name"],
                "复杂度": r["complexity"],
                "基础平均分": r["avg_score"],
                "加权平均分": r["avg_weighted_score"],
                "达标": "是" if r["meets_round_requirement"] >= 50 else "否", 
                "问诊轮数": r["rounds"]
            } for r in results])
            
            # 保存结果到Excel
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"问诊质量评估报告_{timestamp}.xlsx"
            report.to_excel(output_file, index=False)
            
            print("\n=== 问诊质量分析报告 ===")
            stats = report.groupby("复杂度").agg({
            "基础平均分": "mean",
            "加权平均分": "mean",
            "达标": lambda x: f"{sum(1 for v in x if v == '是') / len(x):.1%}",
            "问诊轮数": "mean"
        })        
            # 重命名列
            stats.columns = ["基础平均分", "加权平均分", "达标率", "平均轮数"]
            print(stats.round(2))
            
            print(f"\n评分说明:")
            print(f"- 加权公式: 最终得分 = 基础分×0.8 + 轮次达标×0.2")
            print(f"- 所有工作表的加权平均分: {np.mean([r['avg_weighted_score'] for r in results]):.2f}")
            print(f"- 报告已保存到: {output_file}")

    main()  