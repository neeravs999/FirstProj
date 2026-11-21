"""CLI REPL (FR-18/19). Run with:  python main.py   — type `quit` to exit."""
import os
import sys

from assistant import respond
from chain import friendly_error, source_label
from interaction_log import log_answer
from refund_agent import RefundAgent
from retriever import StoreNotBuiltError


def main() -> None:
    if not os.getenv("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")

    print("Telecom Support Assistant (type 'quit' to exit)\n")
    history: list[dict] = []
    agent = RefundAgent()
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() == "quit":
            break
        if not question:
            continue

        try:
            reply = respond(question, history, agent)
            if reply.stream is not None:
                parts = []
                for i, token in enumerate(reply.stream):
                    print(("Bot: " if i == 0 else "") + token, end="", flush=True)
                    parts.append(token)
                answer = "".join(parts)
            else:
                answer = reply.text
                print(f"Bot: {answer.replace('**', '')}", end="")
        except StoreNotBuiltError as e:
            sys.exit(str(e))
        except Exception as e:
            print(f"\n{friendly_error(e)}\n")
            continue

        if reply.docs:
            print("\n\nSources:")
            for d in reply.docs:
                print(f"  - {source_label(d)}")
        print("\n")
        log_answer(question, answer, [d.metadata["doc_id"] for d in reply.docs], "cli",
                   reply.intent)
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]

    print("Goodbye!")


if __name__ == "__main__":
    main()
