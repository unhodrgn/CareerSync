// Synthetic sample data for the design-review prototype, shown on screen labeled 예시. Shapes follow the API
// (backend/app/schemas, main:frontend/src/api/types.ts). Nothing here is real or comes from a server.

export type Role = 'seeker' | 'company';
export type EmploymentType = 'full_time' | 'contract' | 'intern';
export type JobStatus = 'draft' | 'published' | 'closed';
export type Category = 'skill' | 'experience' | 'project' | 'certificate' | 'education' | 'other';
export type ApplicationStatus = 'submitted' | 'reviewing' | 'interview' | 'on_hold' | 'passed' | 'rejected';
export type EvaluationStatus = 'pending' | 'done' | 'failed';
/** RecommendedJob.match_level: 매우 적합 / 적합 / 참고 (D16). */
export type MatchLevel = 'very' | 'good' | 'ref';
export type Importance = 'core' | 'important' | 'normal';
export type OfferStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled' | 'expired';

/** "Today" for deadlines and expiry in the prototype. */
export const TODAY = '2026-10-16';

export const EMPLOYMENT_TYPES: EmploymentType[] = ['full_time', 'contract', 'intern'];
export const CATEGORIES: Category[] = ['skill', 'experience', 'project', 'certificate', 'education', 'other'];
export const APPLICATION_STATUSES: ApplicationStatus[] = ['submitted', 'reviewing', 'interview', 'on_hold', 'passed', 'rejected'];

// ── Companies ──

export interface CompanyProject {
  id: number;
  name: string;
  description: string;
  techs: string[];
}

export interface Company {
  id: number;
  name: string;
  intro: string;
  talent_profile: string;
  projects: CompanyProject[];
}

export const COMPANIES: Company[] = [
  {
    id: 1,
    name: '클라우드랩',
    intro: '클라우드랩은 제조·물류 기업의 현장 데이터를 모아 분석하는 데이터 플랫폼을 만듭니다. 고객사 120여 곳의 데이터가 매일 저희 파이프라인을 지나갑니다.',
    talent_profile: '문제를 데이터로 정의하고, 판단의 근거를 동료와 투명하게 나누는 사람을 찾습니다. 직접 만든 파이프라인을 끝까지 책임지는 태도를 중요하게 봅니다.',
    projects: [
      {
        id: 11,
        name: '물류 수요 예측 파이프라인',
        description: '전국 물류 센터의 출고 기록을 모아 센터별 일 단위 수요를 예측합니다.',
        techs: ['Python', 'Airflow', 'Spark', 'AWS'],
      },
      {
        id: 12,
        name: '공장 센서 데이터 수집 플랫폼',
        description: '설비 센서에서 초당 수만 건의 이벤트를 받아 실시간 이상 탐지에 넘깁니다.',
        techs: ['Kafka', 'Go', 'PostgreSQL'],
      },
    ],
  },
  {
    id: 2,
    name: '넥스트코드',
    intro: '넥스트코드는 중소 쇼핑몰을 위한 주문·정산 SaaS를 운영합니다.',
    talent_profile: '코드 리뷰에서 이유를 설명할 수 있는 개발자, 운영 이슈를 기록으로 남기는 개발자를 찾습니다.',
    projects: [{ id: 21, name: '정산 엔진 재작성', description: '월 거래 300만 건을 처리하는 정산 배치를 다시 설계합니다.', techs: ['Java', 'Spring', 'PostgreSQL'] }],
  },
  {
    id: 3,
    name: '모아헬스',
    intro: '모아헬스는 병원과 환자를 잇는 건강 기록 앱을 만듭니다.',
    talent_profile: '사용자의 불편을 직접 확인하고, 작은 개선을 자주 배포하는 사람을 찾습니다.',
    projects: [],
  },
  {
    id: 4,
    name: '하이브리지',
    intro: '하이브리지는 항만 물류 데이터를 분석해 선적 일정을 최적화합니다.',
    talent_profile: '현장 담당자와 대화하며 데이터를 해석하는 분석가를 찾습니다.',
    projects: [],
  },
];

export const companyById = (id: number) => COMPANIES.find((c) => c.id === id)!;

// ── Jobs and criteria ──

export interface Criterion {
  id: number;
  name: string;
  description: string;
  category: Category;
  /** Company-only. Never shown to seekers (D1). */
  weight: number;
}

/**
 * The label signed-in seekers see instead of the weight (D30). The cut-offs are the backend's current
 * IMPORTANCE_HIGH / IMPORTANCE_MID, used here only for the sample; D30 does not fix them.
 */
export function importanceOf(weight: number): Importance {
  if (weight >= 25) return 'core';
  if (weight >= 10) return 'important';
  return 'normal';
}

export interface Job {
  id: number;
  company_id: number;
  company_name: string;
  title: string;
  description: string;
  employment_type: EmploymentType;
  /** null = 신입 가능 (D14) */
  min_experience_years: number | null;
  location: string;
  salary_note: string;
  deadline: string | null;
  expired: boolean;
  status: JobStatus;
  published_at: string | null;
  criteria: Criterion[];
  /** Company job list only */
  applicant_count: number;
}

const JD_DATA_ENGINEER = `클라우드랩 데이터플랫폼팀은 고객사 현장 데이터를 수집·정제해 분석팀과 고객에게 전달합니다.

주요 업무
- Airflow 기반 배치 파이프라인 설계와 운영
- Spark로 대용량 출고·센서 데이터 정제
- AWS(S3, EMR, Glue) 위의 데이터 레이크 운영

자격 요건
- Python으로 데이터 처리 코드를 작성하고 운영한 경험
- 배치 또는 스트리밍 파이프라인을 2년 이상 운영한 경험
- 컴퓨터공학·소프트웨어·통계 관련 전공

우대 사항
- Kafka 등 메시지 큐 운영 경험
- 빅데이터분석기사 등 관련 자격`;

const JD_SHORT = (lines: string[]) => lines.join('\n');

export const JOBS: Job[] = [
  {
    id: 101,
    company_id: 1,
    company_name: '클라우드랩',
    title: '데이터 엔지니어',
    description: JD_DATA_ENGINEER,
    employment_type: 'full_time',
    min_experience_years: 2,
    location: '경기 성남시 판교',
    salary_note: '회사 내규에 따름',
    deadline: '2026-11-15',
    expired: false,
    status: 'published',
    published_at: '2026-10-06',
    applicant_count: 6,
    criteria: [
      { id: 1, name: 'Python 활용 능력', description: 'pandas·PySpark로 대용량 데이터 처리', category: 'skill', weight: 30 },
      { id: 2, name: '데이터 파이프라인 경험', description: '배치·스트리밍 파이프라인 설계와 운영 2년 이상', category: 'experience', weight: 30 },
      { id: 3, name: 'AWS 클라우드 운영 경험', description: 'S3, EMR, Glue 운영', category: 'skill', weight: 20 },
      { id: 4, name: '컴퓨터공학 관련 전공', description: '컴퓨터공학·소프트웨어·통계 관련 전공', category: 'education', weight: 20 },
    ],
  },
  {
    id: 102,
    company_id: 1,
    company_name: '클라우드랩',
    title: 'MLOps 엔지니어',
    description: JD_SHORT([
      '수요 예측 모델을 안정적으로 배포하고 운영할 MLOps 엔지니어를 찾습니다.',
      '',
      '주요 업무',
      '- 모델 학습·배포 파이프라인 구축',
      '- Kubernetes 위의 모델 서빙 운영',
    ]),
    employment_type: 'full_time',
    min_experience_years: 3,
    location: '경기 성남시 판교',
    salary_note: '',
    deadline: '2026-12-01',
    expired: false,
    status: 'draft',
    published_at: null,
    applicant_count: 0,
    criteria: [
      { id: 21, name: 'Kubernetes 운영 경험', description: '프로덕션 클러스터 운영', category: 'skill', weight: 30 },
      { id: 22, name: 'ML 모델 서빙 경험', description: '모델을 API로 배포해 운영한 경험', category: 'experience', weight: 30 },
      { id: 23, name: 'Python 활용 능력', description: '', category: 'skill', weight: 20 },
      { id: 24, name: '20대 후반 지원자 우대', description: '팀 평균 연령에 맞는 지원자', category: 'other', weight: 20 },
    ],
  },
  {
    id: 103,
    company_id: 1,
    company_name: '클라우드랩',
    title: '데이터 분석가 (인턴)',
    description: JD_SHORT(['고객사 데이터 리포트를 함께 만들 인턴을 찾습니다.']),
    employment_type: 'intern',
    min_experience_years: null,
    location: '경기 성남시 판교',
    salary_note: '',
    deadline: '2026-09-30',
    expired: true,
    status: 'closed',
    published_at: '2026-09-01',
    applicant_count: 14,
    criteria: [
      { id: 31, name: 'SQL 활용 능력', description: '', category: 'skill', weight: 50 },
      { id: 32, name: '분석 프로젝트 경험', description: '', category: 'project', weight: 50 },
    ],
  },
  {
    id: 201,
    company_id: 2,
    company_name: '넥스트코드',
    title: '백엔드 개발자 (Java/Spring)',
    description: JD_SHORT([
      '정산 엔진과 주문 API를 함께 만들 백엔드 개발자를 찾습니다.',
      '',
      '자격 요건',
      '- Java 17, Spring Boot 실무 경험',
      '- PostgreSQL 쿼리 튜닝 경험',
    ]),
    employment_type: 'full_time',
    min_experience_years: 3,
    location: '서울 강남구',
    salary_note: '',
    deadline: '2026-11-30',
    expired: false,
    status: 'published',
    published_at: '2026-10-08',
    applicant_count: 0,
    criteria: [
      { id: 41, name: 'Java 활용 능력', description: 'Java 17, 컬렉션·동시성 이해', category: 'skill', weight: 30 },
      { id: 42, name: 'Spring 경험', description: 'Spring Boot, JPA 실무 경험', category: 'skill', weight: 25 },
      { id: 43, name: 'DB 경험', description: 'PostgreSQL 쿼리 튜닝, 인덱스 설계', category: 'skill', weight: 20 },
      { id: 44, name: '프로젝트 경험', description: 'API 서버를 직접 설계·배포한 경험', category: 'project', weight: 15 },
      { id: 45, name: '관련 자격증', description: '정보처리기사 등', category: 'certificate', weight: 10 },
    ],
  },
  {
    id: 202,
    company_id: 2,
    company_name: '넥스트코드',
    title: '프론트엔드 개발자 (React)',
    description: JD_SHORT(['판매자 관리 화면을 만들 프론트엔드 개발자를 찾습니다.', '', '자격 요건', '- React, TypeScript 경험']),
    employment_type: 'full_time',
    min_experience_years: null,
    location: '서울 강남구',
    salary_note: '',
    deadline: '2026-10-31',
    expired: false,
    status: 'published',
    published_at: '2026-10-02',
    applicant_count: 0,
    criteria: [
      { id: 51, name: 'React 경험', description: '', category: 'skill', weight: 50 },
      { id: 52, name: 'TypeScript', description: '', category: 'skill', weight: 30 },
      { id: 53, name: 'UI 프로젝트 경험', description: '', category: 'project', weight: 20 },
    ],
  },
  {
    id: 301,
    company_id: 3,
    company_name: '모아헬스',
    title: 'Android 개발자 (인턴)',
    description: JD_SHORT(['건강 기록 앱의 Android 화면을 함께 만들 인턴을 찾습니다.']),
    employment_type: 'intern',
    min_experience_years: null,
    location: '서울 마포구',
    salary_note: '',
    deadline: '2026-10-25',
    expired: false,
    status: 'published',
    published_at: '2026-10-10',
    applicant_count: 0,
    criteria: [
      { id: 61, name: 'Kotlin 활용 능력', description: '', category: 'skill', weight: 40 },
      { id: 62, name: 'Android 앱 프로젝트', description: '', category: 'project', weight: 40 },
      { id: 63, name: '정보처리기사', description: '', category: 'certificate', weight: 20 },
    ],
  },
  {
    id: 302,
    company_id: 3,
    company_name: '모아헬스',
    title: '데이터 플랫폼 엔지니어',
    description: JD_SHORT([
      '병원 연동 데이터를 받아 정제하는 플랫폼을 운영합니다.',
      '',
      '자격 요건',
      '- Kafka 또는 메시지 큐 운영 경험',
      '- Spark 배치 작업 경험',
    ]),
    employment_type: 'contract',
    min_experience_years: 1,
    location: '서울 마포구',
    salary_note: '',
    deadline: null,
    expired: false,
    status: 'published',
    published_at: '2026-10-12',
    applicant_count: 0,
    criteria: [
      { id: 71, name: 'Kafka 운영 경험', description: '', category: 'skill', weight: 35 },
      { id: 72, name: 'Spark 경험', description: '', category: 'skill', weight: 35 },
      { id: 73, name: '데이터 프로젝트 경험', description: '', category: 'project', weight: 30 },
    ],
  },
  {
    id: 401,
    company_id: 4,
    company_name: '하이브리지',
    title: '물류 데이터 분석가',
    description: JD_SHORT(['선적 데이터를 분석해 현장 담당자와 개선안을 만듭니다.']),
    employment_type: 'full_time',
    min_experience_years: 1,
    location: '부산 해운대구',
    salary_note: '',
    deadline: '2026-10-10',
    expired: true,
    status: 'published',
    published_at: '2026-09-15',
    applicant_count: 0,
    criteria: [
      { id: 81, name: 'SQL 활용 능력', description: '', category: 'skill', weight: 40 },
      { id: 82, name: 'Python 활용 능력', description: '', category: 'skill', weight: 30 },
      { id: 83, name: '물류 도메인 경험', description: '', category: 'other', weight: 30 },
    ],
  },
];

export const jobById = (id: number) => JOBS.find((j) => j.id === id);
/** Jobs a guest or seeker can browse (D4): published, not drafts. */
export const PUBLIC_JOBS = JOBS.filter((j) => j.status === 'published');
/** The signed-in company in the prototype. */
export const MY_COMPANY = COMPANIES[0];
export const MY_JOBS = JOBS.filter((j) => j.company_id === MY_COMPANY.id);

// ── Users ──

export const SEEKER_USER = {
  display_name: '정하린',
  email: 'harin.jung@example.com',
  role: 'seeker' as Role,
  consent_version: '2026-10-13',
  consent_privacy_at: '2026-10-02',
  consent_ai_at: '2026-10-02',
  created_at: '2026-10-02',
};

export const COMPANY_USER = {
  display_name: '클라우드랩 채용담당',
  email: 'recruit@cloudlab.example',
  role: 'company' as Role,
};

export const CURRENT_CONSENT_VERSION = '2026-10-13';

// ── Seeker: CV (cv_profile.v1) ──

export interface Experience {
  org: string;
  role: string;
  start: string | null;
  end: string | null;
  description: string;
  source: string;
}
export interface Project {
  name: string;
  role: string;
  tech: string[];
  description: string;
  source: string;
}
export interface Education {
  school: string;
  major: string;
  degree: string;
  source: string;
}
export interface Certificate {
  name: string;
  date: string | null;
  source: string;
}
export interface CvProfile {
  skills: string[];
  experiences: Experience[];
  projects: Project[];
  education: Education[];
  certificates: Certificate[];
  summary: string;
}
export interface Cv {
  id: number;
  file_name: string;
  pages: number;
  version: number;
  profile: CvProfile;
  method: string;
  confirmed: boolean;
  confirmed_at: string | null;
  masked_kinds: string[];
  total_experience_months: number;
  created_at: string;
}

export const CV: Cv = {
  id: 7,
  file_name: 'resume_2026_fall.pdf',
  pages: 2,
  version: 1,
  method: 'rules',
  confirmed: false,
  confirmed_at: null,
  masked_kinds: ['name', 'email', 'phone'],
  total_experience_months: 43,
  created_at: '2026-10-15',
  profile: {
    summary: '물류 데이터 배치 파이프라인을 3년 넘게 운영한 데이터 엔지니어입니다.',
    skills: ['Python', 'SQL', 'Airflow', 'Spark', 'PostgreSQL', 'Docker'],
    experiences: [
      {
        org: '(주)데이터웨이브',
        role: '데이터 엔지니어',
        start: '2023-03',
        end: null,
        description: 'Airflow 기반 일 배치 파이프라인 40여 개 설계·운영, Spark 정제 작업 성능 개선',
        source: 'Airflow 기반 일 배치 파이프라인 40여 개 설계·운영 (2023.03–현재)',
      },
      {
        org: '(주)스마트물류',
        role: '데이터 분석 인턴',
        start: '2022-03',
        end: '2022-08',
        description: '출고 데이터 정합성 검사를 Python으로 자동화',
        source: '출고 데이터 정합성 검사를 Python 스크립트로 자동화 (2022.03–2022.08)',
      },
    ],
    projects: [
      {
        name: '창고 재고 이상 탐지',
        role: '개인 프로젝트',
        tech: ['Python', 'Spark', 'PostgreSQL'],
        description: '재고 변동 로그에서 이상치를 찾아 알림을 보내는 배치',
        source: 'Spark로 재고 변동 로그 2억 건을 일 단위로 집계해 이상치 알림',
      },
    ],
    education: [{ school: '한결대학교', major: '컴퓨터학부', degree: '학사', source: '한결대학교 컴퓨터학부 졸업 (2022.02)' }],
    certificates: [{ name: '정보처리기사', date: '2021-11', source: '정보처리기사 (2021.11)' }],
  },
};

// ── Seeker: recommendations, preferences, job prep ──

export interface RecommendedJob {
  job_id: number;
  match_level: MatchLevel;
}

/** GET /api/recommendations/jobs: band only, no Fit/Pref/Final/scores/weights (D1, D16). */
export const RECOMMENDATIONS: { items: RecommendedJob[]; pending_count: number } = {
  items: [
    { job_id: 101, match_level: 'very' },
    { job_id: 302, match_level: 'very' },
    { job_id: 201, match_level: 'good' },
    { job_id: 202, match_level: 'ref' },
  ],
  pending_count: 2,
};

export const PREFERENCES = {
  locations: ['서울', '경기 성남시'],
  employment_types: ['full_time', 'contract'] as EmploymentType[],
  job_keywords: ['데이터 엔지니어', 'Spark'],
  profile_public: true,
  profile_public_at: '2026-10-02',
};

export interface CareerGap {
  name: string;
  kind: 'skill' | 'certificate';
}
export interface RoadmapStep {
  order: number;
  skill: string;
  kind: 'skill' | 'certificate';
  goal: string;
  activities: string[];
  resources: { title: string; url: string }[];
}
export interface InterviewQuestion {
  question: string;
  criterion_name: string | null;
  kind: 'technical' | 'experience' | 'behavioral';
  intent: string;
  answer_tips: string[];
  cv_quote: string | null;
}
export interface CvReviewItem {
  title: string;
  detail: string;
  cv_quote: string | null;
  affects_scoring: boolean;
}

/** Job prep for job 101 (D21, D25). Rules mode output. */
export const PREP = {
  gaps: [
    { name: 'AWS', kind: 'skill' },
    { name: 'Kafka', kind: 'skill' },
    { name: '빅데이터분석기사', kind: 'certificate' },
  ] as CareerGap[],
  steps: [
    {
      order: 1,
      skill: 'AWS',
      kind: 'skill',
      goal: '지금 운영하는 Spark 배치를 AWS 위에서 한 번 실행해 본다',
      activities: ['S3 버킷에 샘플 데이터를 올리고 접근 권한(IAM)을 구성하기', '기존 PySpark 작업 하나를 EMR에서 실행하기', '실행 시간과 비용을 기록해 이력서 프로젝트 항목에 적기'],
      resources: [{ title: 'Amazon EMR 공식 문서', url: 'https://docs.aws.amazon.com/emr/' }],
    },
    {
      order: 2,
      skill: 'Kafka',
      kind: 'skill',
      goal: '스트리밍 수집의 기본 구조(토픽, 파티션, 컨슈머 그룹)를 익힌다',
      activities: ['로컬 Docker로 브로커 하나를 띄우고 토픽 만들기', '재고 변동 로그를 프로듀서로 보내고 컨슈머로 집계하기'],
      resources: [{ title: 'Apache Kafka 공식 문서', url: 'https://kafka.apache.org/documentation/' }],
    },
    {
      order: 3,
      skill: '빅데이터분석기사',
      kind: 'certificate',
      goal: '시험 과목과 일정을 확인하고 응시 계획을 세운다',
      activities: ['필기 4과목 범위를 확인하기', '다음 회차 접수 일정을 달력에 적기'],
      resources: [{ title: '데이터자격검정 (한국데이터산업진흥원)', url: 'https://www.dataq.or.kr/' }],
    },
  ] as RoadmapStep[],
  questions: [
    {
      question: 'Airflow로 운영한 배치 파이프라인 중 실패가 가장 잦았던 작업은 무엇이었고, 어떻게 안정화했나요?',
      criterion_name: '데이터 파이프라인 경험',
      kind: 'experience',
      intent: '파이프라인을 운영하며 장애를 다룬 경험과 원인 분석 방식을 확인합니다.',
      answer_tips: ['실패 원인을 데이터·코드·인프라 중 어디서 찾았는지 순서대로 말하기', '재발 방지를 위해 바꾼 것(재시도, 알림, 테스트)을 구체적으로 말하기'],
      cv_quote: 'Airflow 기반 일 배치 파이프라인 40여 개 설계·운영 (2023.03–현재)',
    },
    {
      question: 'Spark 작업에서 데이터 쏠림(skew)이 생기면 어떻게 알아차리고 해결하나요?',
      criterion_name: 'Python 활용 능력',
      kind: 'technical',
      intent: '대용량 처리에서 성능 문제를 진단하는 기본기를 확인합니다.',
      answer_tips: ['Spark UI에서 확인하는 지표를 말하기', '솔팅, 브로드캐스트 조인 등 해결책의 장단점 비교하기'],
      cv_quote: 'Spark로 재고 변동 로그 2억 건을 일 단위로 집계해 이상치 알림',
    },
    {
      question: '클라우드 환경에서 데이터 레이크를 운영한다면 비용을 어떻게 관리하겠습니까?',
      criterion_name: 'AWS 클라우드 운영 경험',
      kind: 'technical',
      intent: 'AWS 운영 경험이 이력서에 없을 때, 개념 이해와 학습 계획을 확인합니다.',
      answer_tips: ['경험이 없다면 솔직하게 말하고, 학습 중인 내용을 구체적으로 말하기', '스토리지 계층, 수명 주기 정책 같은 개념을 예로 들기'],
      cv_quote: null,
    },
    {
      question: '분석팀이 요청한 데이터 형식이 운영 원칙과 맞지 않을 때 어떻게 조율했나요?',
      criterion_name: null,
      kind: 'behavioral',
      intent: '동료와 근거를 나누며 일하는 방식을 확인합니다.',
      answer_tips: ['상황, 내 판단, 합의 결과 순서로 말하기'],
      cv_quote: null,
    },
  ] as InterviewQuestion[],
  review: {
    strengths: [
      {
        title: '운영 경험이 기간과 규모로 드러납니다',
        detail: '파이프라인 개수와 기간이 함께 적혀 있어 경력을 확인하기 쉽습니다.',
        cv_quote: 'Airflow 기반 일 배치 파이프라인 40여 개 설계·운영 (2023.03–현재)',
        affects_scoring: false,
      },
      {
        title: 'Python과 Spark를 여러 항목에서 사용했습니다',
        detail: '경력과 프로젝트 양쪽에 같은 기술이 나와 실제 사용 근거가 됩니다.',
        cv_quote: 'Spark로 재고 변동 로그 2억 건을 일 단위로 집계해 이상치 알림',
        affects_scoring: false,
      },
    ],
    improvements: [
      {
        title: 'Docker는 PDF 원문에서 찾을 수 없습니다',
        detail: '확인 화면에서 추가한 기술은 평가에 반영되지 않습니다. 사용한 경험을 이력서 PDF에 적어 다시 올려 주세요.',
        cv_quote: null,
        affects_scoring: true,
      },
      {
        title: '프로젝트에 기간이 없습니다',
        detail: '프로젝트 기간을 적으면 경력과 겹치는지 읽는 사람이 판단하기 쉽습니다.',
        cv_quote: 'Spark로 재고 변동 로그 2억 건을 일 단위로 집계해 이상치 알림',
        affects_scoring: true,
      },
      {
        title: '성과를 숫자로 적은 항목이 하나뿐입니다',
        detail: '처리 시간 단축, 장애 감소처럼 바뀐 결과를 숫자로 적어 보세요.',
        cv_quote: null,
        affects_scoring: false,
      },
    ],
  } as { strengths: CvReviewItem[]; improvements: CvReviewItem[] },
};

// ── Offers (D20) ──

export interface SeekerOffer {
  offer_id: number;
  company_name: string;
  job_id: number;
  message: string | null;
  status: OfferStatus;
  created_at: string;
  expires_at: string;
  responded_at: string | null;
}

export const SEEKER_OFFERS: SeekerOffer[] = [
  {
    offer_id: 1,
    company_name: '클라우드랩',
    job_id: 101,
    message: '안녕하세요, 클라우드랩 데이터플랫폼팀입니다. 공개하신 프로필의 Airflow·Spark 운영 경험이 저희 수요 예측 파이프라인과 잘 맞아 연락드립니다. 관심 있으시면 수락해 주세요.',
    status: 'pending',
    created_at: '2026-10-14',
    expires_at: '2026-10-28',
    responded_at: null,
  },
  {
    offer_id: 2,
    company_name: '모아헬스',
    job_id: 302,
    message: null,
    status: 'pending',
    created_at: '2026-10-09',
    expires_at: '2026-10-23',
    responded_at: null,
  },
  {
    offer_id: 3,
    company_name: '넥스트코드',
    job_id: 201,
    message: '정산 엔진 재작성 프로젝트에 함께할 분을 찾고 있습니다.',
    status: 'accepted',
    created_at: '2026-09-28',
    expires_at: '2026-10-12',
    responded_at: '2026-09-30',
  },
  {
    offer_id: 4,
    company_name: '하이브리지',
    job_id: 401,
    message: null,
    status: 'expired',
    created_at: '2026-09-16',
    expires_at: '2026-09-30',
    responded_at: null,
  },
];

// ── Company: applicants and evaluations (job 101) ──

export interface CriterionEvaluation {
  criterion_id: number;
  score: number;
  reason: string;
  evidence: string[];
  method: string;
}

export interface Applicant {
  application_id: number;
  name: string;
  email: string;
  status: ApplicationStatus;
  applied_at: string;
  experience_months: number;
  evaluation_status: EvaluationStatus;
  summary: string;
  items: CriterionEvaluation[];
}

const ev = (criterion_id: number, score: number, reason: string, evidence: string[], method = 'rules'): CriterionEvaluation => ({
  criterion_id,
  score,
  reason,
  evidence,
  method,
});

export const APPLICANTS: Applicant[] = [
  {
    application_id: 501,
    name: '김서연',
    email: 'seoyeon.kim@example.com',
    status: 'interview',
    applied_at: '2026-10-07',
    experience_months: 38,
    evaluation_status: 'done',
    summary: 'Airflow·Spark 배치 파이프라인을 3년 넘게 운영했고, EMR 운영 근거가 있습니다.',
    items: [
      ev(1, 95, 'Python으로 Spark 작업과 품질 검사를 작성한 근거가 여러 항목에 있습니다.', ['PySpark로 일 4억 건 출고 로그 정제 작업 작성', 'Python 데이터 품질 검사 라이브러리를 사내 표준으로 도입']),
      ev(2, 92, '배치 파이프라인 운영 기간이 요구 2년을 넘습니다.', ['Airflow·Spark 배치 파이프라인 3년 운영 (2023.01–현재)']),
      ev(3, 85, 'EMR 클러스터 운영과 S3 데이터 레이크 구성 근거가 있습니다.', ['EMR 클러스터 비용을 스팟 인스턴스로 38% 절감']),
      ev(4, 100, '전공이 기준에 적힌 전공과 일치합니다.', ['한빛대학교 컴퓨터공학과 졸업 (2020.02)']),
    ],
  },
  {
    application_id: 502,
    name: '이준호',
    email: 'junho.lee@example.com',
    status: 'reviewing',
    applied_at: '2026-10-09',
    experience_months: 30,
    evaluation_status: 'done',
    summary: '파이프라인 운영 경험은 기준을 충족하고, AWS는 S3·Glue 사용 근거가 있습니다.',
    items: [
      ev(1, 80, 'Python 사용 근거가 경력 항목에 있습니다.', ['Python으로 ETL 스크립트 30여 개 유지보수']),
      ev(2, 70, '파이프라인 운영 경험이 요구 기간을 충족합니다.', ['NiFi 기반 수집 파이프라인 2년 6개월 운영']),
      ev(3, 75, 'S3와 Glue 사용 근거가 있습니다.', ['Glue 카탈로그로 S3 데이터 레이크 테이블 관리']),
      ev(4, 100, '전공이 기준에 적힌 전공과 일치합니다.', ['세움대학교 통계학과 졸업 (2021.02)']),
    ],
  },
  {
    application_id: 503,
    name: '박도윤',
    email: 'doyun.park@example.com',
    status: 'submitted',
    applied_at: '2026-10-11',
    experience_months: 26,
    evaluation_status: 'done',
    summary: 'Python과 파이프라인 경험은 충분하지만, AWS 운영 근거는 한 줄뿐입니다.',
    items: [
      ev(1, 88, 'Python 자동화 근거가 있습니다.', ['Python으로 데이터 정합성 검사 자동화']),
      ev(2, 85, '배치 파이프라인 운영 기간이 요구 2년을 넘습니다.', ['Luigi 배치 파이프라인 2년 2개월 운영']),
      ev(3, 30, 'AWS는 학습 경험만 적혀 있고 운영 근거는 없습니다.', ['AWS 기초 온라인 강의 수료']),
      ev(4, 100, '전공이 기준에 적힌 전공과 일치합니다.', ['누리대학교 소프트웨어학과 졸업 (2022.02)']),
    ],
  },
  {
    application_id: 504,
    name: '최민지',
    email: 'minji.choi@example.com',
    status: 'on_hold',
    applied_at: '2026-10-12',
    experience_months: 14,
    evaluation_status: 'done',
    summary: 'Python 사용 근거는 있으나 파이프라인 운영 기간이 짧습니다.',
    items: [
      ev(1, 70, 'Python 사용 근거가 프로젝트 항목에 있습니다.', ['Python으로 공공데이터 수집기 작성']),
      ev(2, 45, '파이프라인 운영 기간이 요구 2년에 못 미칩니다.', ['Airflow DAG 운영 1년 2개월']),
      ev(3, 40, 'AWS 사용 근거가 개인 프로젝트에만 있습니다.', ['개인 프로젝트를 EC2에 배포']),
      ev(4, 0, '기준에 적힌 전공을 이력서에서 찾지 못했습니다.', []),
    ],
  },
  {
    application_id: 505,
    name: '한지우',
    email: 'jiwoo.han@example.com',
    status: 'submitted',
    applied_at: '2026-10-15',
    experience_months: 0,
    evaluation_status: 'pending',
    summary: '',
    items: [],
  },
  {
    application_id: 506,
    name: '오세훈',
    email: 'sehoon.oh@example.com',
    status: 'submitted',
    applied_at: '2026-10-15',
    experience_months: 0,
    evaluation_status: 'failed',
    summary: '',
    items: [],
  },
];

/** STRONG_SCORE: a criterion score at or above it counts as a strength. */
export const STRONG_SCORE = 70;

export function fitOf(a: Applicant, criteria: Criterion[]): number | null {
  if (a.evaluation_status !== 'done') return null;
  const total = criteria.reduce((sum, c) => sum + c.weight, 0);
  const s = criteria.reduce((sum, c) => sum + (a.items.find((i) => i.criterion_id === c.id)?.score ?? 0) * c.weight, 0);
  return Math.round((s / total) * 10) / 10;
}

// ── Company: talent (D19) and sent offers (D20) ──

export interface AnonymousProfile {
  skills: string[];
  experience_years: number;
  roles: string[];
  project_techs: string[];
  education: { degree: string; major: string }[];
  certificates: string[];
  desired: { locations: string[]; employment_types: EmploymentType[]; job_keywords: string[] };
}

export interface TalentCandidate extends AnonymousProfile {
  anonymous_id: string;
  fit: number;
  criteria: { criterion_id: number; score: number }[];
  offer_status: OfferStatus | null;
}

export const TALENT: { items: TalentCandidate[]; pending_count: number } = {
  pending_count: 1,
  items: [
    {
      anonymous_id: 'T-8K2M4Q',
      fit: 84,
      criteria: [
        { criterion_id: 1, score: 90 },
        { criterion_id: 2, score: 88 },
        { criterion_id: 3, score: 80 },
        { criterion_id: 4, score: 70 },
      ],
      skills: ['Python', 'Spark', 'Kafka', 'AWS', 'SQL'],
      experience_years: 4,
      roles: ['데이터 엔지니어'],
      project_techs: ['Kafka', 'Flink', 'S3'],
      education: [{ degree: '학사', major: '통계학' }],
      certificates: ['SQLD'],
      desired: { locations: ['경기 성남시', '서울'], employment_types: ['full_time'], job_keywords: ['데이터 엔지니어'] },
      offer_status: null,
    },
    {
      anonymous_id: 'T-3RX9PA',
      fit: 77,
      criteria: [
        { criterion_id: 1, score: 85 },
        { criterion_id: 2, score: 80 },
        { criterion_id: 3, score: 55 },
        { criterion_id: 4, score: 100 },
      ],
      skills: ['Python', 'Airflow', 'PostgreSQL', 'Docker'],
      experience_years: 3,
      roles: ['데이터 엔지니어', '백엔드 개발자'],
      project_techs: ['Airflow', 'FastAPI'],
      education: [{ degree: '학사', major: '컴퓨터공학' }],
      certificates: ['정보처리기사'],
      desired: { locations: ['서울'], employment_types: ['full_time', 'contract'], job_keywords: ['데이터', 'Python'] },
      offer_status: 'pending',
    },
    {
      anonymous_id: 'T-Q7D1LM',
      fit: 69,
      criteria: [
        { criterion_id: 1, score: 75 },
        { criterion_id: 2, score: 60 },
        { criterion_id: 3, score: 70 },
        { criterion_id: 4, score: 70 },
      ],
      skills: ['Python', 'AWS', 'Terraform'],
      experience_years: 2,
      roles: ['클라우드 엔지니어'],
      project_techs: ['AWS Lambda', 'S3'],
      education: [{ degree: '석사', major: '산업공학' }],
      certificates: ['AWS Certified Solutions Architect'],
      desired: { locations: ['경기 성남시'], employment_types: ['full_time'], job_keywords: ['데이터 엔지니어', '클라우드'] },
      offer_status: null,
    },
    {
      anonymous_id: 'T-5NW8CE',
      fit: 62,
      criteria: [
        { criterion_id: 1, score: 80 },
        { criterion_id: 2, score: 45 },
        { criterion_id: 3, score: 40 },
        { criterion_id: 4, score: 100 },
      ],
      skills: ['Python', 'pandas', 'SQL'],
      experience_years: 1,
      roles: ['데이터 분석가'],
      project_techs: ['pandas', 'scikit-learn'],
      education: [{ degree: '학사', major: '소프트웨어' }],
      certificates: [],
      desired: { locations: ['서울', '경기'], employment_types: ['full_time', 'intern'], job_keywords: ['데이터'] },
      offer_status: null,
    },
  ],
};

export interface SentOffer {
  offer_id: number;
  job_id: number | null;
  job_title: string | null;
  anonymous_id: string;
  message: string | null;
  status: OfferStatus;
  created_at: string;
  expires_at: string;
  responded_at: string | null;
  /** null while the seeker is not public (opt-in off or AI consent withdrawn) */
  candidate: AnonymousProfile | null;
  /** Only after the seeker accepted: display_name + email (D3, D20) */
  contact: { display_name: string; email: string } | null;
}

export const SENT_OFFERS: SentOffer[] = [
  {
    offer_id: 91,
    job_id: 101,
    job_title: '데이터 엔지니어',
    anonymous_id: 'T-6HJ2KX',
    message: '수요 예측 파이프라인 팀에서 함께 일하실 분을 찾고 있습니다.',
    status: 'accepted',
    created_at: '2026-10-02',
    expires_at: '2026-10-16',
    responded_at: '2026-10-05',
    candidate: TALENT.items[0],
    contact: { display_name: '윤태경', email: 'taekyung.yoon@example.com' },
  },
  {
    offer_id: 92,
    job_id: 101,
    job_title: '데이터 엔지니어',
    anonymous_id: 'T-3RX9PA',
    message: '공개 프로필의 Airflow 경험을 보고 연락드립니다.',
    status: 'pending',
    created_at: '2026-10-14',
    expires_at: '2026-10-28',
    responded_at: null,
    candidate: TALENT.items[1],
    contact: null,
  },
  {
    offer_id: 93,
    job_id: 101,
    job_title: '데이터 엔지니어',
    anonymous_id: 'T-2MN7RT',
    message: null,
    status: 'pending',
    created_at: '2026-10-11',
    expires_at: '2026-10-25',
    responded_at: null,
    candidate: null,
    contact: null,
  },
  {
    offer_id: 94,
    job_id: 103,
    job_title: '데이터 분석가 (인턴)',
    anonymous_id: 'T-1LP0ZB',
    message: null,
    status: 'rejected',
    created_at: '2026-09-10',
    expires_at: '2026-09-24',
    responded_at: '2026-09-12',
    candidate: TALENT.items[3],
    contact: null,
  },
  {
    offer_id: 95,
    job_id: 101,
    job_title: '데이터 엔지니어',
    anonymous_id: 'T-9VC3UE',
    message: null,
    status: 'expired',
    created_at: '2026-09-20',
    expires_at: '2026-10-04',
    responded_at: null,
    candidate: TALENT.items[2],
    contact: null,
  },
];

// ── Company: AI JD draft and criteria suggestions (D24) ──

export const JD_DRAFT = {
  method: 'rules',
  sections: {
    intro: '클라우드랩은 제조·물류 기업의 현장 데이터를 모아 분석하는 데이터 플랫폼을 만듭니다. 수요 예측 모델을 안정적으로 운영할 MLOps 엔지니어를 찾습니다.',
    responsibilities: ['모델 학습·배포 파이프라인 구축과 운영', 'Kubernetes 위의 모델 서빙 환경 운영', '물류 수요 예측 파이프라인과 모델 배포 연동'],
    requirements: ['Kubernetes 운영 경험', 'Python으로 ML 파이프라인을 작성한 경험', '모델을 API로 배포해 운영한 경험 3년 이상'],
    preferred: ['Airflow, Spark 사용 경험', 'AWS 운영 경험'],
  },
  dropped: [
    { text: '연봉은 6천만 원 이상으로 협의합니다.', reason: '급여·금액은 AI 초안에 넣지 않습니다. 급여 안내는 직접 입력해 주세요.' },
    { text: '20대 후반의 젊은 팀원을 우대합니다.', reason: '연령은 모집·채용에서 차별 사유로 사용할 수 없습니다. (고령자고용법 제4조의4)' },
  ],
};

export const SUGGESTED_CRITERIA = {
  items: [
    { name: 'Kubernetes 운영 경험', category: 'skill' as Category, weight: 35, description: '자격 요건에서 추출' },
    { name: 'ML 모델 서빙 경험', category: 'experience' as Category, weight: 35, description: '자격 요건에서 추출' },
    { name: 'Python 활용 능력', category: 'skill' as Category, weight: 30, description: '자격 요건에서 추출' },
  ],
  blocked: [{ name: '관련 전공', code: 'CRITERIA_MAJOR_REQUIRED', reason: '학력 기준에는 전공을 하나 이상 적어야 합니다.' }],
};

// ── Legal guardrail (a few rules of data/blocklist.yaml, for the prototype only) ──

export interface GuardrailHit {
  index: number;
  rule_id: string;
  matched: string;
  reason: string;
  law_ref: string;
}

const RULES: { id: string; pattern: RegExp; reason: string; law_ref: string }[] = [
  {
    id: 'age',
    pattern: /\d{2}\s*(세|살)\s*(이하|이상|미만|까지|이내)|[2-6]0\s*대\s*(초반|중반|후반|우대|선호|한정|지원자|이하|이상)?|연령|나이|젊은/,
    reason: '연령은 모집·채용에서 차별 사유로 사용할 수 없습니다.',
    law_ref: '고령자고용법 제4조의4',
  },
  {
    id: 'gender',
    pattern: /남성|여성|남자|여자|성별|출산\s*(계획|예정|여부)/,
    reason: '성별·임신·출산 계획은 모집·채용에서 차별 사유로 사용할 수 없습니다.',
    law_ref: '남녀고용평등법 제7조',
  },
  {
    id: 'physical.appearance',
    pattern: /용모|외모|외형|체격|몸매/,
    reason: '용모·외모는 직무 수행과 무관한 신체 조건이므로 평가 기준으로 사용할 수 없습니다.',
    law_ref: '채용절차법 제4조의3 제1호',
  },
  {
    id: 'origin.marital',
    pattern: /혼인|기혼|미혼|결혼/,
    reason: '혼인 여부는 직무 수행과 무관하므로 평가 기준으로 사용할 수 없습니다.',
    law_ref: '채용절차법 제4조의3 제2호',
  },
];

/** Checks criterion names and descriptions the way PUT /criteria does on save. */
export function checkCriteria(items: { name: string; description: string }[]): GuardrailHit[] {
  const hits: GuardrailHit[] = [];
  items.forEach((c, index) => {
    const text = `${c.name} ${c.description}`;
    for (const r of RULES) {
      const m = text.match(r.pattern);
      if (m) {
        hits.push({ index, rule_id: r.id, matched: m[0].trim(), reason: r.reason, law_ref: r.law_ref });
        break;
      }
    }
  });
  return hits;
}

// ── Helpers ──

export function daysUntil(date: string): number {
  return Math.round((Date.parse(date) - Date.parse(TODAY)) / 86_400_000);
}

export function formatDate(date: string): string {
  const [y, m, d] = date.split('-');
  return `${y}.${m}.${d}`;
}
