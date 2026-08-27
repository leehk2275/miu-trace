from __future__ import annotations

import json
from backend.app.miu_hub import INDEX, sync


def main() -> None:
    payload = sync()
    print(json.dumps({"output": str(INDEX), "products": len(payload["products"]), "events": len(payload["events"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
