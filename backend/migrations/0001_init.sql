CREATE TABLE users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    kakao_subject VARCHAR(64) NULL,
    phone_number VARCHAR(15) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(50) NOT NULL,
    birth_year SMALLINT NOT NULL,
    gender VARCHAR(10) NOT NULL,
    marital_status VARCHAR(10) NOT NULL,
    is_employed BOOLEAN NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'customer',
    failed_login_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT uq_users_kakao_subject UNIQUE (kakao_subject),
    CONSTRAINT uq_users_phone_number UNIQUE (phone_number),
    CONSTRAINT chk_users_birth_year CHECK (birth_year >= 1900),
    CONSTRAINT chk_users_gender CHECK (gender IN ('male', 'female')),
    CONSTRAINT chk_users_marital CHECK (marital_status IN ('single', 'married')),
    CONSTRAINT chk_users_role CHECK (role IN ('customer', 'bank_employee'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 로그인 세션. 쿠키에는 세션 값 원본, DB에는 그 SHA-256 해시만 둔다. 끝난 세션도 지우지 않는다.
CREATE TABLE sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    token_hash CHAR(64) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    device_id CHAR(36) NOT NULL,
    client VARCHAR(16) NOT NULL DEFAULT 'web',
    user_agent VARCHAR(255) NULL,
    login_method VARCHAR(16) NOT NULL DEFAULT 'password',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_seen_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6) NULL,
    end_reason VARCHAR(16) NULL,
    CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash),
    KEY ix_sessions_user_device (user_id, device_id, ended_at),
    CONSTRAINT chk_sessions_client CHECK (client IN ('web', 'ios-app', 'android-app')),
    CONSTRAINT chk_sessions_login_method CHECK (login_method IN ('password', 'kakao')),
    CONSTRAINT chk_sessions_end_reason CHECK (end_reason IN ('logout', 'replaced', 'idle_timeout', 'max_age')),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 카카오 인증은 끝났지만 아직 가입 화면을 마치지 않은 사람(5분). 가입이 끝나면 지운다.
CREATE TABLE kakao_signups (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    token_hash CHAR(64) NOT NULL,
    kakao_subject VARCHAR(64) NOT NULL,
    name VARCHAR(50) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NOT NULL,
    CONSTRAINT uq_kakao_signups_token_hash UNIQUE (token_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    account_number VARCHAR(20) NOT NULL,
    balance BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT uq_accounts_user UNIQUE (user_id),
    CONSTRAINT uq_accounts_number UNIQUE (account_number),
    CONSTRAINT chk_accounts_balance CHECK (balance >= 0),
    CONSTRAINT fk_accounts_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE cards (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id BIGINT UNSIGNED NOT NULL,
    card_number CHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT uq_cards_account UNIQUE (account_id),
    CONSTRAINT uq_cards_number UNIQUE (card_number),
    CONSTRAINT fk_cards_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE merchants (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(20) NOT NULL,
    region VARCHAR(30) NOT NULL,
    lat DECIMAL(9, 6) NOT NULL,
    lng DECIMAL(9, 6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE ledger_entries (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    transaction_id CHAR(36) NOT NULL,
    account_id BIGINT UNSIGNED NOT NULL,
    entry_type VARCHAR(20) NOT NULL,
    amount BIGINT NOT NULL,
    balance_after BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY ix_ledger_account_created (account_id, created_at),
    KEY ix_ledger_transaction (transaction_id),
    CONSTRAINT chk_ledger_type CHECK (entry_type IN ('deposit', 'withdrawal', 'transfer_out', 'transfer_in',
        'loan_disbursement', 'loan_repayment', 'card_payment')),
    CONSTRAINT chk_ledger_amount CHECK (amount <> 0),
    CONSTRAINT chk_ledger_balance_after CHECK (balance_after >= 0),
    CONSTRAINT fk_ledger_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE card_payments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    card_id BIGINT UNSIGNED NOT NULL,
    merchant_id BIGINT UNSIGNED NOT NULL,
    transaction_id CHAR(36) NOT NULL,
    amount BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY ix_card_payments_card_created (card_id, created_at),
    CONSTRAINT chk_card_payments_amount CHECK (amount > 0),
    CONSTRAINT fk_card_payments_card FOREIGN KEY (card_id) REFERENCES cards (id),
    CONSTRAINT fk_card_payments_merchant FOREIGN KEY (merchant_id) REFERENCES merchants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE loan_products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(16) NOT NULL,
    name VARCHAR(50) NOT NULL,
    min_amount BIGINT NOT NULL,
    max_amount BIGINT NOT NULL,
    amount_step BIGINT NOT NULL,
    term_options JSON NOT NULL,
    CONSTRAINT uq_loan_products_code UNIQUE (code),
    CONSTRAINT chk_loan_products_amount CHECK (min_amount > 0 AND min_amount <= max_amount AND amount_step > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE loan_applications (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    product_code VARCHAR(16) NOT NULL,
    principal_amount BIGINT NOT NULL,
    term_months SMALLINT UNSIGNED NOT NULL,
    monthly_installment BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by BIGINT UNSIGNED NULL,
    reviewed_at DATETIME(6) NULL,
    approved_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY ix_loan_applications_user_status (user_id, status),
    KEY ix_loan_applications_status_id (status, id),
    CONSTRAINT chk_loan_applications_status CHECK (status IN ('pending', 'repaying', 'rejected', 'repaid')),
    CONSTRAINT chk_loan_applications_amount CHECK (principal_amount > 0 AND term_months > 0 AND monthly_installment > 0),
    CONSTRAINT fk_loan_applications_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_loan_applications_product FOREIGN KEY (product_id) REFERENCES loan_products (id),
    CONSTRAINT fk_loan_applications_reviewer FOREIGN KEY (reviewed_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE loan_repayments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    loan_application_id BIGINT UNSIGNED NOT NULL,
    installment_number SMALLINT UNSIGNED NOT NULL,
    due_date DATE NOT NULL,
    amount BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'scheduled',
    processed_at DATETIME(6) NULL,
    paid_at DATETIME(6) NULL,
    CONSTRAINT uq_loan_repayments_installment UNIQUE (loan_application_id, installment_number),
    KEY ix_loan_repayments_status_due (status, due_date),
    CONSTRAINT chk_loan_repayments_status CHECK (status IN ('scheduled', 'paid', 'overdue')),
    CONSTRAINT chk_loan_repayments_amount CHECK (amount > 0),
    CONSTRAINT fk_loan_repayments_application FOREIGN KEY (loan_application_id) REFERENCES loan_applications (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
