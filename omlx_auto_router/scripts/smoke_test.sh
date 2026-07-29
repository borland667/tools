#!/usr/bin/env bash
set -euo pipefail

ROUTER_URL="${ROUTER_URL:-http://127.0.0.1:8010}"
OMLX_API_KEY="${OMLX_API_KEY:-sk-local}"

echo "== Health =="
curl -fsS "$ROUTER_URL/health" | jq .

echo
echo "== Auto aliases =="
curl -fsS "$ROUTER_URL/v1/models"   -H "Authorization: Bearer $OMLX_API_KEY"   | jq '[.data[].id | select(. == "auto" or . == "auto-chat" or . == "auto-agent")]'

echo
echo "== Auto Chat =="
curl -fsS "$ROUTER_URL/v1/chat/completions"   -H "Content-Type: application/json"   -H "Authorization: Bearer $OMLX_API_KEY"   -d '{
    "model": "auto-chat",
    "messages": [
      {
        "role": "user",
        "content": "Investigate intermittent PostgreSQL timeouts and return a short hypothesis list."
      }
    ],
    "max_tokens": 256,
    "temperature": 0.1
  }' | jq '{
    upstream_model: .model,
    route: .auto_router.route,
    selected_model: .auto_router.model,
    source: .auto_router.source,
    content: .choices[0].message.content
  }'

echo
echo "== Embeddings =="
curl -fsS "$ROUTER_URL/v1/embeddings"   -H "Content-Type: application/json"   -H "Authorization: Bearer $OMLX_API_KEY"   -d '{
    "model": "auto",
    "input": "authentication login token validation"
  }' | jq '{
    model,
    dimensions: (.data[0].embedding | length),
    usage
  }'

echo
echo "== Reranking =="
curl -fsS "$ROUTER_URL/v1/rerank"   -H "Content-Type: application/json"   -H "Authorization: Bearer $OMLX_API_KEY"   -d '{
    "model": "auto",
    "query": "Where is authentication implemented?",
    "documents": [
      "auth/login.py handles user login and token validation",
      "billing/invoices.py creates monthly invoices",
      "README.md contains setup instructions"
    ]
  }' | jq .
