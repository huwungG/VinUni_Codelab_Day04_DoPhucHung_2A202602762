"""
Lab #4: System Prompt Engineering & Tool Calling Engine
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.

Kiến trúc:
  - ChatbotBaseline: LLM thuần, không dùng tool → quan sát hallucination.
  - ToolCallingAgent: Agent dùng System Prompt + 2 Tool Schemas.
"""

import json
import re
from typing import Dict, Any, List
from tools import TOOL_DEFINITIONS, TOOL_MAP, search_product_catalog, submit_support_ticket

# ═══════════════════════════════════════════════════════════════════════════
# TODO 1: Thiết kế SYSTEM PROMPT cấp sản xuất
# Yêu cầu: Phải chứa Persona, Core Rules, Operational Boundaries, Output Contract.
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
# VinAssistant — Trợ lý AI chính thức của Vingroup

## 1. PERSONA
Bạn là VinAssistant, trợ lý hỗ trợ khách hàng của hệ sinh thái Vingroup
(VinFast, Vinpearl, Vinhomes). Giọng nói chuyên nghiệp, thân thiện, rõ ràng.

## 2. AVAILABLE TOOLS
Bạn được phép dùng các tool sau:
{tools}

## 3. CORE RULES
- Không bịa giá, tồn kho hay chính sách.
- Khi khách hỏi sản phẩm/giá → bắt buộc gọi search_product_catalog.
- Khi khách báo lỗi/khiếu nại/yêu cầu hỗ trợ → bắt buộc gọi submit_support_ticket.
- Câu FAQ chính sách có thể trả lời trực tiếp nếu không cần dữ liệu realtime.

## 4. OPERATIONAL BOUNDARIES
- Chỉ trả lời về sản phẩm/dịch vụ Vingroup.
- Từ chối lịch sự các chủ đề ngoài phạm vi Vingroup.

## 5. OUTPUT CONTRACT
Thought: ...
Action: tool_name(args)  OR  Final Answer: ...
Observation: ...
Final Answer: câu trả lời cuối cùng bằng tiếng Việt, ngắn gọn, dựa trên dữ liệu tool.
"""


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ChatbotBaseline
# ═══════════════════════════════════════════════════════════════════════════

class ChatbotBaseline:
    """Baseline LLM Chatbot — Không sử dụng Tool Calling hay ReAct Loop."""

    def query(self, user_input: str) -> Dict[str, Any]:
        # TODO 2: Trả về câu trả lời tĩnh (mock) hoặc gọi Gemini API 1 lượt (không dùng tool)
        # Mục tiêu: Quan sát hiện tượng bịa thông tin (hallucination)
        return {
            "answer": f"[Chatbot Baseline] Trả lời cho: {user_input}",
            "tool_calls": [],
            "status": "success",
            "mode": "mock_baseline"
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ToolCallingAgent
# ═══════════════════════════════════════════════════════════════════════════

class ToolCallingAgent:
    """Agent với System Prompt Engineering & Tool Calling."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace: List[Dict[str, Any]] = []

    def run(self, user_input: str) -> Dict[str, Any]:
        """Điểm vào chính — chạy Agent Loop."""
        self.trace = []
        text = user_input.lower()

        # TODO 3: Phân tích intent từ user_input
        need_ticket = any(k in text for k in [
            "lỗi", "ticket", "hỗ trợ", "khiếu nại", "phản hồi", "nghiêm trọng", "xử lý gấp"
        ])
        need_catalog = any(k in text for k in [
            "xe điện", "vinfast", "giá dưới", "resort", "vinpearl", "du lịch", "xem xe"
        ]) and not need_ticket
        is_faq = any(k in text for k in ["bảo hành", "chính sách"]) and not need_ticket

        # TODO 4: Xây dựng Agent Loop (while iteration <= self.max_iterations)
        iteration = 0
        answer = ""

        while iteration < self.max_iterations:
            iteration += 1

            if is_faq:
                answer = (
                    "Chính sách bảo hành pin xe điện VinFast kéo dài đến 10 năm "
                    "hoặc theo điều kiện bảo hành chính hãng VinFast."
                )
                self.trace.append({
                    "step": iteration,
                    "thought": "FAQ — trả lời trực tiếp không cần tool",
                    "action": None,
                    "observation": None,
                    "final_answer": answer,
                })
                break

            if need_catalog:
                category = "du_lich" if any(k in text for k in ["resort", "vinpearl", "du lịch"]) else "xe_dien"
                max_price = 999999999999
                m = re.search(r"dưới\s+(\d+(?:[.,]\d+)?)\s*(triệu|tỷ)?", text)
                if m:
                    value = float(m.group(1).replace(",", "."))
                    unit = m.group(2) or "triệu"
                    max_price = int(value * (1_000_000_000 if unit == "tỷ" else 1_000_000))

                results = search_product_catalog(category=category, max_price=max_price)
                self.trace.append({
                    "step": iteration,
                    "thought": "Cần tra cứu catalog",
                    "action": "search_product_catalog",
                    "args": {"category": category, "max_price": max_price},
                    "observation": results,
                })

                if not results:
                    answer = "Rất tiếc, không tìm thấy sản phẩm phù hợp với yêu cầu của bạn."
                else:
                    lines = []
                    for p in results:
                        lines.append(f"- {p['name']}: {p['price_vnd']:,} VNĐ — {p.get('description', '')}")
                    answer = "Các sản phẩm phù hợp:\n" + "\n".join(lines)
                break

            if need_ticket:
                name_match = re.search(r"tên\s+([^,.]+)", user_input, re.IGNORECASE)
                customer_name = name_match.group(1).strip() if name_match else "Khách hàng"
                priority = "high" if any(k in text for k in ["nghiêm trọng", "gấp", "khẩn"]) else "medium"
                issue_match = re.search(r"(xe .+?)(?:\.|$)", user_input, re.IGNORECASE)
                issue_description = issue_match.group(1).strip() if issue_match else user_input

                ticket = submit_support_ticket(
                    customer_name=customer_name,
                    issue_description=issue_description,
                    priority=priority,
                )
                self.trace.append({
                    "step": iteration,
                    "thought": "Cần tạo ticket hỗ trợ",
                    "action": "submit_support_ticket",
                    "args": {
                        "customer_name": customer_name,
                        "issue_description": issue_description,
                        "priority": priority,
                    },
                    "observation": ticket,
                })
                answer = (
                    f"Đã tạo ticket {ticket['ticket_id']} cho khách hàng {customer_name}. "
                    f"Ưu tiên: {ticket['priority']}. Trạng thái: {ticket['status']}."
                )
                break

            answer = "Xin lỗi, tôi chỉ hỗ trợ các câu hỏi liên quan đến sản phẩm và dịch vụ Vingroup."
            self.trace.append({
                "step": iteration,
                "thought": "Ngoài phạm vi",
                "action": None,
                "final_answer": answer,
            })
            break

        return {
            "answer": answer,
            "trace": self.trace,
            "iterations": iteration,
            "status": "completed",
        }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Chạy thử nhanh
# ═══════════════════════════════════════════════════════════════════════════

def main():
    user_query = "Tôi muốn xem xe điện VinFast giá dưới 600 triệu."

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING TOOL CALLING AGENT ===")
    agent = ToolCallingAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result["answer"])
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
