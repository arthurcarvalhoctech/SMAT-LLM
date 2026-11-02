USER_ID=$(id -u) GROUP_ID=$(id -g)   docker compose run --rm --build smat bash -lc 'cd /app && python3 run_experiment.py'
