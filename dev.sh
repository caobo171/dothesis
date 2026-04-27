#!/bin/bash

# Start MongoDB + Redis
echo "Starting MongoDB and Redis..."
docker-compose -f docker/docker-compose.yml up -d

# Start backend in a subshell so the cd doesn't bleed into this script's cwd.
echo "Starting backend on port 8001..."
( cd backend && npm run dev ) &
BACKEND_PID=$!

# Start frontend the same way. The previous version did `cd backend && npm run dev &`
# which only cd'd in the backgrounded subshell, then `cd ..` moved the parent
# shell out of the project root, breaking the next `cd frontend`.
echo "Starting frontend on port 8002..."
( cd frontend && npm run dev ) &
FRONTEND_PID=$!

echo ""
echo "Services running:"
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:8002"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait and handle Ctrl+C
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID; docker-compose -f docker/docker-compose.yml stop; exit 0" INT
wait

