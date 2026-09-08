# 발행 대시보드

글 하나를 **홈페이지 · 네이버 블로그 · 티스토리 · 구글 블로거** 네 곳에 올린다.

```bash
python3 tools/publisher/server.py
```

브라우저가 열린다. 처음 한 번만 각 채널에서 **로그인** 버튼을 누르고,
그다음부터는 **발행** 버튼만 누르면 된다.

## 왜 이렇게 만들었나

네이버와 카카오(티스토리)는 아이디·비밀번호 자동 입력을 막는다. 캡차, 새 기기
확인, 2단계 인증이 번갈아 나온다. 코드로 뚫으면 며칠 못 가서 다시 막힌다.

그래서 **로그인만 사람이 한다.** 로그인 버튼을 누르면 진짜 크롬 창이 뜨고,
거기서 평소처럼 로그인하면 된다. 로그인이 끝나면 그 세션(쿠키)만
`.publish-session/` 에 저장하고 창을 닫는다. 발행은 그 세션으로 자동으로 한다.

**비밀번호는 어디에도 저장하지 않는다.**

## 저장되는 것

| 파일 | 내용 |
|---|---|
| `.publish-session/naver.json` | 네이버 로그인 쿠키 |
| `.publish-session/tistory.json` | 티스토리(카카오) 로그인 쿠키 |
| `.publish-session/blogger.json` | 구글 OAuth 리프레시 토큰 |
| `.publish-session/config.json` | 기본 주소를 이 컴퓨터에서만 바꿀 때 |

이 폴더는 `.gitignore` 에 들어 있다. 계정 그 자체나 마찬가지이므로
**저장소에 올리면 안 된다.** 파일 권한도 600 으로 둔다.

세션은 영원하지 않다. 네이버는 몇 주, 카카오도 비슷하다. 발행이 "로그인 세션이
없거나 만료됐습니다" 로 끝나면 로그인 버튼을 한 번 더 누르면 된다.

## 채널별 준비물

### 홈페이지
없다. `git push` 가 곧 발행이다.

### 네이버 블로그
로그인 버튼만 누르면 된다. 블로그 아이디는 `data/blog-targets.json` 에
`kucoom7` 로 적어 두었다. 비워 두면 로그인한 계정에서 알아낸다.

### 티스토리
로그인 버튼만 누르면 된다. 블로그 주소는 `data/blog-targets.json` 에
`worldtraveler1` 로 적어 두었다. 블로그를 옮기면 그 파일만 고치면 된다.

### 구글 블로거
쿠키가 아니라 OAuth 라서 준비물이 하나 더 있다.

1. 구글 클라우드 콘솔 → API 및 서비스 → **Blogger API v3** 사용 설정
2. 사용자 인증 정보 → OAuth 클라이언트 ID → 유형 **데스크톱 앱**
3. 나온 클라이언트 ID·시크릿을 대시보드의 블로거 칸에 넣고 로그인
4. OAuth 동의 화면을 **프로덕션**으로 게시할 것 —
   '테스트' 상태면 토큰이 7일 만에 만료된다

## 글은 어디에 두나

`blog-exports/<슬러그>/` 안에 채널별 원고를 둔다.

```
blog-exports/아유타야/
  ├─ 네이버블로그.txt   [제목란] [카테고리] [본문] [태그란] 블록
  ├─ 티스토리.html      머리말 주석에 제목·카테고리·태그
  ├─ 블로거.html        --- front matter --- 에 title·labels
  └─ meta.json          홈페이지·블로거 파일 연결, 메모
```

도입부는 채널마다 조금씩 다르게 쓴다. 같은 글이 네 군데에 똑같이 올라가면
검색에서 서로를 깎아먹는다.

발행 대상 주소는 `data/blog-targets.json` 에 있다. 로그인 정보가 아니라
주소일 뿐이라 저장소에 둔다.

```json
{
  "NAVER_BLOG_ID": "kucoom7",
  "TISTORY_BLOG_NAME": "worldtraveler1",
  "BLOGGER_BLOG_URL": "https://worldtraveler111.blogspot.com"
}
```

`meta.json`:

```json
{
  "title": "아유타야 당일치기",
  "date": "2026-03-24",
  "site": "posts/ayutthaya.html",
  "blogger": "blogger-posts/ayutthaya.html"
}
```

같은 글을 두 번 올리지 않도록 `data/blog-published.json` 과
`data/blogger-published.json` 에 기록이 남는다. 대시보드의 ✓ 표시가 그것이다.

## 명령줄로도 된다

```bash
python3 tools/publisher/login.py naver
python3 tools/publisher/login.py tistory
python3 tools/publisher/login.py blogger --client-id ... --client-secret ...

ONLY_SLUG=아유타야 python3 .github/scripts/publish-to-naver.py
ONLY_SLUG=아유타야 python3 .github/scripts/publish-to-tistory.py
ONLY_SLUG=ayutthaya python3 .github/scripts/publish-to-blogger.py
```

## 깃허브 액션에서도 올리려면

액션에는 브라우저 앞에 앉을 사람이 없으니 로그인을 할 수 없다. 대신 이미
받아 둔 세션을 넣어 주면 된다.

대시보드의 채널 줄에 있는 **[깃허브용 값 복사]** 버튼을 누르면 세션 내용이
클립보드에 들어온다. 그걸 저장소 → Settings → Secrets and variables →
Actions → New repository secret 에 붙여넣는다.
이름은 각각 `NAVER_SESSION_JSON`, `TISTORY_SESSION_JSON`.
`blog-exports/**` 가 바뀌어 push 되면 워크플로가 알아서 올린다.
secret 이 없으면 그 채널만 조용히 건너뛰고, 왜 건너뛰었는지 로그에 적는다.

**이 값은 로그인한 상태 그 자체다.** 가진 사람은 비밀번호 없이도 계정에
들어갈 수 있다. 저장소가 공개라면 secret 이라도 넣지 않는 편이 낫다.
그리고 액션 러너는 미국 IP 라서, 네이버가 낯선 접속으로 보고 막을 수 있다.

세션이 만료되면 다시 로그인해서 secret 도 다시 넣어야 한다. 이게 번거로우면
그냥 내 컴퓨터에서 대시보드를 쓰는 편이 낫다 — 그쪽이 원래 설계다.

## 잘 안 될 때

발행이 실패하면 `publish-debug/` 에 그 시점의 화면과 HTML 이 남는다.
네이버·티스토리 에디터는 화면 구조가 자주 바뀌므로, 대개는 각 스크립트
맨 위의 셀렉터 상수를 그 스크린샷에 맞춰 고치면 된다.
