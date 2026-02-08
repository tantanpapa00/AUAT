#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RTF 파일 생성 - 한글을 유니코드 이스케이프로 변환"""

content = """BBooster 이용약관

제1조 (목적)
본 약관은 큐브시스템(이하 "회사")이 제공하는 BBooster 서비스의 이용 조건을 규정합니다.

제2조 (불법 복제 금지)
1. 본 소프트웨어의 무단 복제, 배포, 역공학을 금지합니다.
2. 위반 시 관련 법률에 따라 민형사상 책임을 질 수 있습니다.

제3조 (API 키 관리 책임)
1. 사용자가 등록한 거래소/증권사 API 키는 사용자 본인이 관리합니다.
2. API 키 유출로 인한 손실은 회사가 책임지지 않습니다.
3. API 키는 반드시 출금 권한을 제외하고 생성하시기 바랍니다.

제4조 (투자 책임)
1. BBooster를 통한 모든 투자 판단과 결과는 사용자 본인의 책임입니다.
2. 자동매매 기능 사용 시 발생하는 손실에 대해 회사는 책임지지 않습니다.
3. 과거 수익률이 미래 수익을 보장하지 않습니다.

제5조 (서비스 중단)
1. 시스템 점검, 장애, 천재지변 등으로 서비스가 중단될 수 있습니다.
2. 서비스 중단으로 인한 매매 손실에 대해 회사는 책임지지 않습니다.

제6조 (개인정보)
1. 회사는 서비스 제공을 위해 최소한의 개인정보를 수집합니다.
2. 수집된 정보는 서비스 제공 목적 외에 사용하지 않습니다.

제7조 (비밀번호)
1. 12자리 이상, 영문/숫자/특수문자 포함이 필수입니다.
2. 분실 시 재설정 가능합니다.

본 약관에 동의하지 않으면 BBooster를 설치 및 사용할 수 없습니다.

Copyright 2026 큐브시스템(QUBE System). All rights reserved.
"""

# RTF 유니코드 변환
rtf_lines = []
for line in content.split('\n'):
    rtf_line = ""
    for ch in line:
        if ord(ch) > 127:
            rtf_line += f"\\u{ord(ch)}?"
        else:
            rtf_line += ch
    rtf_lines.append(rtf_line)

rtf_body = "\\par\n".join(rtf_lines)

rtf_content = r"""{\rtf1\ansi\deff0
{\fonttbl{\f0\fswiss\fcharset0 Arial;}}
\f0\fs20
""" + rtf_body + r"""
}"""

with open("LICENSE_KO.rtf", "w", encoding="ascii") as f:
    f.write(rtf_content)

print("LICENSE_KO.rtf 생성 완료")
