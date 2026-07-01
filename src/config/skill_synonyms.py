"""
Skill synonym dictionary.

Keys   = canonical skill name (how we store it internally)
Values = list of known aliases / misspellings / abbreviations

Loaded by SkillNormalizer in Phase 4.
"""

SKILL_SYNONYMS: dict[str, list[str]] = {
    # ── Languages ──────────────────────────────────────────────────────────
    "Python": ["python", "python3", "py", "python 3"],
    "JavaScript": ["javascript", "js", "java script", "ecmascript", "es6"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java", "java8", "java 8", "java 11", "java 17"],
    "Go": ["go", "golang"],
    "Rust": ["rust", "rust-lang"],
    "C++": ["c++", "cpp", "c plus plus"],
    "C#": ["c#", "csharp", "c sharp", ".net c#"],
    "Ruby": ["ruby", "ruby on rails", "ror"],
    "Scala": ["scala"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "PHP": ["php"],
    "R": ["r", "r-lang", "r language"],
    "SQL": ["sql", "mysql", "structured query language"],

    # ── Frameworks ─────────────────────────────────────────────────────────
    "React": ["react", "reactjs", "react.js"],
    "Angular": ["angular", "angularjs", "angular.js"],
    "Vue.js": ["vue", "vuejs", "vue.js"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    "Node.js": ["node", "nodejs", "node.js"],
    "Express.js": ["express", "expressjs", "express.js"],
    "Next.js": ["next", "nextjs", "next.js"],

    # ── Data / ML ──────────────────────────────────────────────────────────
    "Apache Spark": ["spark", "apache spark", "pyspark"],
    "Apache Kafka": ["kafka", "apache kafka"],
    "Apache Airflow": ["airflow", "apache airflow"],
    "dbt": ["dbt", "data build tool"],
    "TensorFlow": ["tensorflow", "tf"],
    "PyTorch": ["pytorch", "torch"],
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Matplotlib": ["matplotlib"],
    "Seaborn": ["seaborn"],
    "XGBoost": ["xgboost", "xgb"],
    "LightGBM": ["lightgbm", "lgbm"],
    "Hugging Face": ["hugging face", "huggingface", "transformers"],

    # ── Databases ──────────────────────────────────────────────────────────
    "PostgreSQL": ["postgresql", "postgres", "pg"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search", "es"],
    "Cassandra": ["cassandra", "apache cassandra"],
    "BigQuery": ["bigquery", "big query", "google bigquery"],
    "Snowflake": ["snowflake"],
    "Redshift": ["redshift", "amazon redshift", "aws redshift"],

    # ── Cloud & DevOps ─────────────────────────────────────────────────────
    "AWS": ["aws", "amazon web services", "amazon aws"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Azure": ["azure", "microsoft azure"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "CI/CD": ["ci/cd", "cicd", "ci cd", "continuous integration"],
    "GitHub Actions": ["github actions", "gh actions"],
    "Jenkins": ["jenkins"],

    # ── Practices ──────────────────────────────────────────────────────────
    "REST APIs": ["rest", "rest api", "restful", "restful api", "rest apis"],
    "GraphQL": ["graphql"],
    "Microservices": ["microservices", "micro services", "micro-services"],
    "Agile": ["agile", "scrum", "kanban"],
    "TDD": ["tdd", "test driven development", "test-driven development"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "dl"],
    "Data Engineering": ["data engineering", "data pipelines"],
    "ETL": ["etl", "elt", "extract transform load"],
    "System Design": ["system design", "distributed systems"],
}
