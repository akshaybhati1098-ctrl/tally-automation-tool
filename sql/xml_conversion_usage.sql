-- Separate Excel -> Tally XML row allowance.
-- Party Matching limits are intentionally unchanged.

ALTER TABLE subscription_plans
ADD COLUMN IF NOT EXISTS xml_row_limit INTEGER DEFAULT 0;

UPDATE subscription_plans
SET xml_row_limit = CASE
    WHEN LOWER(plan_name) = 'trial' THEN 10
    WHEN LOWER(plan_name) = 'basic' THEN 100
    WHEN LOWER(plan_name) = 'pro' THEN 250
    ELSE COALESCE(xml_row_limit, 0)
END
WHERE LOWER(plan_name) IN ('trial', 'basic', 'pro');

-- XML usage is stored separately from Party Matching usage.
-- Rows are created lazily by the application after the first successful conversion.
