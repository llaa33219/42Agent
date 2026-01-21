# 42Agent

Qwen3-Omni-Flash 기반 자율 AI 에이전트. VM을 실시간으로 보고, 듣고, 조작합니다.

## 특징

- **실시간 옴니모달**: 비디오/오디오 입력 → 음성/텍스트 출력
- **자율 행동**: 명령 없이도 스스로 VM 탐색 및 작업 수행
- **무제한 기억**: RAG 기반 장기 메모리
- **VM 조작**: QEMU 키보드/마우스 제어
- **Live2D 아바타**: 화면 우하단 캐릭터 + 립싱크

## 요구사항

- Python 3.10+
- QEMU
- [DashScope API 키](https://dashscope.console.aliyun.com/)

## 빠른 시작

```bash
# 1. 설정
cp .env.example .env
# .env 파일 편집

# 2. 실행
python3 run.py
```

끝. `run.py`가 가상환경 생성, 패키지 설치, 의존성 검증을 모두 자동으로 처리합니다.

## .env 설정

```bash
DASHSCOPE_API_KEY=your_api_key_here
ISO_PATH=./ubuntu.iso
AVATAR_PATH=./assets/model.json
```

## 조작법

| 키 | 동작 |
|---|------|
| `T` | 채팅창 열기 |
| `ESC` | 채팅창 닫기 |

## 파일 준비

1. **VM ISO**: 설치할 OS 이미지 (예: ubuntu-24.04-desktop-amd64.iso)
2. **Live2D 모델**: model.json 또는 model3.json 파일이 포함된 폴더

## 명령어

```bash
# 의존성 확인만
python run.py --check-only

# 의존성 강제 복구
python run.py --repair

# 클린 재설치
python run.py --clean
```

## 설정

`config/default.yaml`에서 수정:

```yaml
agent:
  voice: "Chelsie"      # 음성 선택

vm:
  memory: "4096"        # VM 메모리 (MB)
  cpus: 2               # CPU 코어 수

avatar:
  position_x: 0.85      # 아바타 X 위치 (0-1)
  position_y: 0.15      # 아바타 Y 위치 (0-1)
  scale: 0.35           # 아바타 크기
```

## 구조

```
42Agent/
├── run.py              # 실행 스크립트
├── config/             # 설정
├── assets/             # Live2D 모델
└── src/
    ├── agent/          # AI 에이전트 코어
    ├── memory/         # RAG 메모리
    ├── vm/             # QEMU 제어
    ├── avatar/         # Live2D 렌더링
    └── ui/             # PyQt6 UI
```

## 라이선스

MIT
