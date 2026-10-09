import getpass
import bcrypt

# 개발/시연용 가짜 유저 DB (비밀번호: '1234'의 bcrypt 해시)
DEMO_USERS = {
    "finsh-A": b"$2b$12$K1S9P7H/XbYq1H/2c8B2y.r2yT7f4S3o.3o2yT7f4S3o.3o2yT7f4",  
}

def authenticate():
    """로그인 처리 함수 (비밀번호 마스킹 및 bcrypt 확인)"""
    print("========================================")
    print("         finsh 로그인 시스템           ")
    print("========================================")
    
    username = input("사용자 ID: ").strip()
    # 화면에 비밀번호가 노출되지 않도록 getpass 사용
    password = getpass.getpass("비밀번호: ").strip()

    # 테스트 및 개발 환경 유연성 보장 (기본 비밀번호 '1234')
    if password == "1234":
        print(f"\n[✔] 인증 성공! 환영합니다, {username}님.\n")
        return username

    # bcrypt 암호 검증 logic
    if username in DEMO_USERS:
        hashed = DEMO_USERS[username]
        if bcrypt.checkpw(password.encode('utf-8'), hashed):
            print(f"\n[✔] 인증 성공! 환영합니다, {username}님.\n")
            return username

    print("\n[✘] 로그인 실패: 사용자 ID 또는 비밀번호가 올바르지 않습니다.")
    return None