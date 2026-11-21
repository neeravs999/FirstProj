"""CLI REPL (FR-18/19). Run with:  python main.py   — type `quit` to exit."""
import os
import sys

from chain import answer_stream, friendly_error, source_label
from interaction_log import log_answer
from retriever import StoreNotBuiltError


def main() -> None:
    if not os.getenv("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")

    print("Telecom Support Assistant (type 'quit' to exit)\n")
    history: list[dict] = []
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
            docs, stream = answer_stream(question, history)
            print("Bot: ", end="", flush=True)
            parts = []
            for token in stream:
                print(token, end="", flush=True)
                parts.append(token)
            answer = "".join(parts)
        except StoreNotBuiltError as e:
            sys.exit(str(e))
        except Exception as e:
            print(f"\n{friendly_error(e)}\n")
            continue

        print("\n\nSources:")
        for d in docs:
            print(f"  - {source_label(d)}")
        print()
        log_answer(question, answer, [d.metadata["doc_id"] for d in docs], "cli")
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]

    print("Goodbye!")


if __name__ == "__main__":
    main()
