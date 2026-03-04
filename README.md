# ParamNerede - Cloud-Native AI Financial Assistant

**Live Demo:** [https://main.doy5nbim771eq.amplifyapp.com/](https://main.doy5nbim771eq.amplifyapp.com/)

> **Note:** This project is a live portfolio demonstration. To optimize cloud costs, it leverages a single-AZ and event-driven asynchronous architecture. Expensive managed services (like NAT Gateways) have been intentionally replaced with budget-friendly alternatives (EC2 NAT Instance). These deviations are documented in the [Demo Constraints](#demo-constraints-vs-production) section.

---

## English

### Project Overview
ParamNerede is a serverless, cloud-native personal finance application backed by generative AI. It was built to demonstrate practical skills in AWS cloud architecture, network security, Infrastructure as Code (IaC) with Terraform, and backend engineering. 

The system acts as a digital financial coach: users can track expenses, manage budgets, upload receipts for automatic OCR extraction, and receive AI-driven insights on their spending habits.

### Architecture Diagram

![AWS Architecture Diagram](diagram.png)

### Key Architectural Decisions

The architecture focuses on system resilience, performance, and cost-efficiency.

1. **Decoupled S3 Uploads:** Files are never proxied through Lambda. The frontend requests a temporary **Presigned URL** and uploads directly to S3. This eliminates compute bottlenecks and strict Lambda payload limits.
2. **Asynchronous Event-Driven AI:** API Gateway has a strict 29-second timeout. Since LLM inference (Bedrock) and OCR (Textract) easily exceed this, the routing Lambda invokes a background worker Lambda (`InvocationType="Event"`) and immediately returns a `202 Accepted`.
3. **Structured AI Insights:** The Worker Lambda aggregates monthly spending, compares it against user-defined budgets, and feeds the data to Claude 3. The LLM then returns structured JSON arrays containing personalized financial warnings, actionable advice, and dynamically detected anomalies, which are rendered on the frontend dashboard.
4. **Mock-Driven CI/CD Testing:** To prevent expensive database provisioning in the pipeline, the backend is covered by `pytest` using `unittest.mock`. This strictly validates business logic and API HTTP status codes without real AWS calls.

### Core Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React.js, Tailwind CSS, AWS Amplify |
| **API** | AWS API Gateway (HTTP APIs) |
| **Compute** | AWS Lambda (Python 3.12) |
| **Generative AI** | Amazon Bedrock (Claude 3 Haiku) |
| **OCR** | Amazon Textract |
| **Database** | Amazon RDS (PostgreSQL 16) |
| **Auth** | Amazon Cognito |
| **Storage** | Amazon S3 |
| **Secrets** | AWS Systems Manager (SSM) Parameter Store |
| **IaC** | HashiCorp Terraform |

### Implementation Details

- **JWT & RBAC Validation:** Cognito JWTs are validated via RS256 algorithm securely *before* core Lambda processing. Role-Based Access Control differentiates `sys-admin` and `developer` groups.
- **Cold-Start Management:** Critical AI Lambda functions are assigned version aliases (`prod`) to standardize deployments and lay the groundwork for provisioned concurrency, mitigating cold-start latency.
- **Cost Optimization:** Cloud costs are optimized by utilizing a single-AZ RDS layout and event-driven async structures.
- **Monitoring & Observability:** Structured JSON logs and AWS X-Ray traces enable end-to-end debugging of asynchronous workflows. OpenTelemetry and Langfuse are deeply integrated to monitor Amazon Bedrock usage, trace LLM generations, and conduct cost/token analysis.
- **API Protection:** API Gateway default throttling protects the system from accidental high-frequency requests.
- **Terraform IaC:** Terraform configuration files were used to structure reusable and maintainable infrastructure definitions across the AWS environment.

### Network & Zero-Trust Security

The Virtual Private Cloud is partitioned to isolate the data layer:
- **Public Subnets:** House the **NAT Instance** (for outbound traffic) and **Bastion Host** (for secure admin SSH access).
- **Private Subnets:** House the Lambdas and RDS. These resources have **no direct inbound internet access**.
- **Security Groups:** 
  - `lambda-sg` only routes outbound via NAT.
  - `rds-sg` explicitly blocks all traffic except incoming port `5432` from `lambda-sg` and `bastion-sg`.

### Demo Constraints vs. Production

To accommodate a trial-tier budget, the current architecture replaces some enterprise features with budget-friendly placeholders:

| Component | Demo Implementation | Production Standard |
|---|---|---|
| **High Availability** | Single-AZ RDS PostgreSQL | Multi-AZ RDS with automatic rapid failover |
| **Outbound Routing** | EC2 NAT Instance | Managed AWS NAT Gateway (Highly available, multi-AZ) |
| **Integration Testing** | Mock-driven pipelines only | Automated E2E integration tests against a live DB clone |
| **Edge Security**| None currently configured | AWS WAF on the API Gateway to block DDoS/OWASP threats |

---

## Türkçe

### Proje Özeti
ParamNerede, üretken yapay zeka (generative AI) gücünü arkasına alan, serverless ve cloud-native bir kişisel finans uygulamasıdır. AWS bulut mimarisi, güvenli ağ tasarımı, Terraform ile altyapı kodlama (IaC) ve backend mühendisliği yetkinliklerini sergilemek amacıyla geliştirilmiştir.

Uygulama, dijital bir finansal koç görevi görür: Kullanıcılar harcamalarını takip edebilir, bütçe yapabilir, fiş görsellerini yükleyerek OCR destekli otomatik veri çekimi yapabilir ve yapay zeka tabanlı analizler alabilir.

### Mimari Diyagram

![Mimari Diyagram](diagram.png)

### Önemli Mimari Kararlar (Key Architectural Decisions)

Mimari tasarım; sistem dayanıklılığına, performansa ve maliyet optimizasyonuna odaklanır:

1. **İzole S3 Yüklemeleri (Decoupled Uploads):** Dosyalar asla doğrudan Lambda üzerinden aktarılmaz. İstemci geçici bir **Presigned URL** alır ve doğrudan S3'e yükleme yapar. Bu karar, gereksiz bellek tüketimini (RAM) ve sistem darboğazlarını önler.
2. **Asenkron Event-Driven YZ:** API Gateway'in kesin 29 saniyelik bir zaman aşımı (timeout) sınırı vardır. LLM analizi (Bedrock) ve OCR (Textract) bu süreyi aşabileceği için, yönlendirici Lambda arka plan işçisini asenkron (`InvocationType="Event"`) tetikler ve kullanıcıya anında `202 Accepted` döner.
3. **Yapılandırılmış YZ Analizleri (Structured AI Insights):** Worker Lambda, kullanıcının aylık harcamalarını toplayıp bütçesiyle kıyaslar ve bu veriyi Claude 3'e besler. LLM; kişiselleştirilmiş finansal uyarılar, hedeflere yönelik tavsiyeler ve tespit edilen anomalileri yapılandırılmış JSON dizileri olarak döndürür ve frontend'de dinamik olarak sergilenmesini sağlar.
4. **Mock Temelli CI/CD Testleri:** Pipeline üzerinde yapılandırma maliyetlerini düşürmek için backend yapısı `unittest.mock` ve `pytest` ile test edilmiştir. Gerçek AWS çağrıları yapılmadan iş mantığı (business logic) ve HTTP dönüş kodları doğrulanır.

### Temel Tech Stack

| Katman | Teknoloji |
|---|---|
| **Frontend** | React.js, Tailwind CSS, AWS Amplify |
| **API** | AWS API Gateway (HTTP APIs) |
| **Compute** | AWS Lambda (Python 3.12) |
| **Generative AI** | Amazon Bedrock (Claude 3 Haiku) |
| **OCR** | Amazon Textract |
| **Database** | Amazon RDS (PostgreSQL 16) |
| **Auth** | Amazon Cognito |
| **Storage** | Amazon S3 |
| **Secrets** | AWS Systems Manager (SSM) Parameter Store |
| **IaC** | HashiCorp Terraform |

### Tasarım ve Uygulama Detayları

- **JWT ve RBAC Doğrulaması:** Cognito JWT'leri, veri işlemeden hemen önce RS256 algoritmasıyla güvenlice doğrulanır ve `sys-admin` / `developer` rolleriyle erişim kontrolü sağlanır.
- **Cold-Start Optimizasyonu:** Kritik yapay zeka Lambda fonksiyonlarına Sürüm Alias'ı (`prod`) atanmış olup, gecikmeyi önleyecek olan Provisioned Concurrency atamasına zemin hazırlanmıştır.
- **Maliyet Optimizasyonu (Cost Optimization):** Bulut maliyetleri, Single-AZ veritabanı kurulumu ve event-driven asenkron mimari kullanılarak optimize edilmiştir.
- **Monitoring ve Gözlemlenebilirlik:** CloudWatch JSON logları ve X-Ray Trace'leri (izleri), asenkron iş akışlarının uçtan uca hata ayıklamasına olanak tanır. Ayrıca OpenTelemetry ve Langfuse entegrasyonu sayesinde Amazon Bedrock istekleri izlenir (LLM tracing) ve token bazlı maliyet analizleri yapılır.
- **Rate Limiting / Güvenlik:** API Gateway'in varsayılan Throttling (hız sınırlama) özellikleri sistemi anlık, yüksek frekanslı istek krizlerine karşı korur.
- **Terraform IaC:** Terraform modülleri (dosyaları), sürdürülebilir ve yeniden kullanılabilir altyapı tanımları oluşturmak için kullanılmıştır.

### Ağ İzolasyonu ve Zero-Trust Güvenlik

Virtual Private Cloud (VPC), veri katmanını dışarıdan görünmez yapacak şekilde bölümlendirilmiştir:
- **Public Subnet'ler:** Dışarı çıkış trafiğini yöneten **NAT Instance** ve ssh bağlantılarına kapı açan **Bastion Host** burada bulunur.
- **Private Subnet'ler:** Lambda'lar ve RDS tam izole çalışır. **İnternetten doğrudan içerik/istek alamazlar.**
- **Güvenlik Grupları (Security Groups):** 
  - `lambda-sg` dışarıya sadece NAT yönünden çıkış yapabilir.
  - `rds-sg` dış dünyayı tamamen engeller; port `5432` trafiğini sadece uygulamadan (`lambda-sg`) ve yönetim makinesinden (`bastion-sg`) kabul eder.

### Demo Kısıtları vs. Production Standardı

Deneme hesap bütçesine sadık kalmak adına, standart bazı kurumsal bileşenler bütçe dostu alternatiflerle değiştirilmiştir:

| Bileşen | Demo Durumu | Production Standardı |
|---|---|---|
| **Yüksek Erişilebilirlik (HA)**| Single-AZ RDS PostgreSQL | Otomatik hata geçişli (failover) Multi-AZ RDS |
| **İnternet Route'u** | EC2 NAT Instance | Tam yönetilen, Multi-AZ destekli AWS NAT Gateway |
| **Tam Kapsam Bütünleşik Test** | Sadece Mock-Driven Unit test altyapısı | CI sürecinde staging veritabanı ile koşan gerçek E2E testleri |
| **Edge Trafik Güvenliği (WAF)**| Mevcut değil | DDoS ve OWASP savunması sağlayan API Gateway önü AWS WAF |
