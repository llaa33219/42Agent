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
- **Live2D 빌드 도구**: cmake, make, gcc (live2d-py 빌드에 필요)

### 시스템 의존성 설치

**Ubuntu/Debian:**
```bash
sudo apt install python3-dev portaudio19-dev qemu-system-x86 qemu-utils cmake make build-essential
```

**Fedora/RHEL:**
```bash
sudo dnf install python3-devel portaudio-devel qemu-system-x86 qemu-img cmake make gcc gcc-c++
```

**Arch Linux:**
```bash
sudo pacman -S python portaudio qemu-full cmake make gcc
```

**macOS:**
```bash
brew install portaudio qemu cmake
```

## 빠른 시작

```bash
# 1. 설정
cp .env.example .env
# .env 파일 편집

# 2. 실행
python3 run.py
```

끝. `run.py`가 가상환경 생성, 패키지 설치, 의존성 검증을 모두 자동으로 처리합니다.

> **참고**: 시스템 의존성(QEMU, cmake, make, gcc)이 없으면 `run.py`가 설치 명령어를 안내합니다.

## .env 설정

```bash
DASHSCOPE_API_KEY=your_api_key_here
ISO_PATH=./linuxmint-22.3-cinnamon-64bit.iso
AVATAR_PATH=./assets/model.json
```

## 조작법

| 키 | 동작 |
|---|------|
| `T` | 채팅창 열기 |
| `ESC` | 채팅창 닫기 |

## 파일 준비

1. **VM ISO**: 설치할 OS 이미지 (예: linuxmint-22.3-cinnamon-64bit.iso)
2. **Live2D 모델**: model.json (Cubism 2) 또는 model3.json (Cubism 3) 파일
   - 예제 모델 포함: `./assets/example/hibiki.model3.json`

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
아파치 2.0
예제 모델의 라이선스는 별도입니다.
(추후 자세하게 수정 예정)