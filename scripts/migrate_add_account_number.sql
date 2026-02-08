-- Migration: Add account_number column to accounts table
-- For existing databases that need the KIS account number support
-- Run: psql -U bbooster -d bbooster -f scripts/migrate_add_account_number.sql

-- Add account_number column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts' AND column_name = 'account_number'
    ) THEN
        ALTER TABLE accounts ADD COLUMN account_number TEXT;
        RAISE NOTICE 'Column account_number added to accounts table';
    ELSE
        RAISE NOTICE 'Column account_number already exists';
    END IF;
END $$;

-- Add password_hash column to users if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'password_hash'
    ) THEN
        ALTER TABLE users ADD COLUMN password_hash TEXT;
        RAISE NOTICE 'Column password_hash added to users table';
    ELSE
        RAISE NOTICE 'Column password_hash already exists';
    END IF;
END $$;

-- Verification
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'accounts'
ORDER BY ordinal_position;
