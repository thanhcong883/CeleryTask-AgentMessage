# Guidelines for Jules

After making any changes to the codebase, you must ensure that the application still functions correctly by running the following verification steps:

## Verification Steps

1. **Cleanup Old Processes:** Run the cleanup script to ensure no stale server, worker, or pytest processes are running.
   ```bash
   ./kill_services.sh
   ```

2. **Run Tests:** Check if the `.env.test` file exists and contains the necessary Telegram credentials.
   - If `.env.test` exists and has `TEST_TELEGRAM_TOKEN` and `TEST_TELEGRAM_GROUP`, run the tests, skipping the manual ones.
   - If not, skip the tests.

   ```bash
   # Use this command to run tests while skipping the manual receipt test:
   if [ -f .env.test ] && grep -q "TEST_TELEGRAM_TOKEN=" .env.test && grep -q "TEST_TELEGRAM_GROUP=" .env.test; then
       pytest -k "not manual"
   else
       echo "Skipping tests: .env.test is missing or incomplete."
   fi
   ```

## Pre-Commit Checklist

- [ ] Run `./kill_services.sh` to clean up the environment.
- [ ] Run `pytest -k "not manual"` (if `.env.test` is available).
- [ ] Ensure all tests pass before submitting.
