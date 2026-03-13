Auto-Cure: Autonomous Bug Detection, Diagnosis, and Fixes Proposal with AI
Mr. Shailesh Galande
Mihir Patil, Pranav Patil, Siddhesh Patil, Prerana Mhatre
Department of Computer Engineering,
Pimpri Chinchwad College of Engineering, Pune, India
Email: sgalande11@gmail.com, {mihir.patil22, pranav.patil221, siddhesh.patil221, prerana.mhatre23}@pccoepune.org 
 
Abstract
This survey examines the emerging paradigm of self-healing software systems that leverage artificial intelligence to autonomously detect, diagnose, and repair software bugs without human intervention. Modern software maintenance consumes 60–70% of development costs, with manual debugging representing a significant bottleneck. The field has evolved from reactive, infrastructure-level resilience to proactive, application-level autonomous repair. This paper explores the state-of-the-art in AI-driven automated program repair, log anomaly detection, and real-time self-healing mechanisms. We synthesize findings from recent research including RepairAgent, SynergyBug, and biological-inspired healing frameworks. The work identifies key research gaps in semantic understanding, multi-language support, continuous learning, and end-to-end automation, proposing an integrated architectural framework that combines log monitoring, AI orchestration, anomaly detection, and automated patch generation.
1. Introduction
1.1 Problem Statement and Motivation
Software development faces an unprecedented maintenance burden. Modern software systems exhibit inherent complexity through constant integration of new features, security patches, and infrastructure upgrades. Manual debugging remains labor-intensive: developers spend significant time identifying root causes, reproducing issues, formulating fixes, and validating corrections. This process incurs substantial costs—with software maintenance consuming 60–70% of total development costs and manual bug fixing representing one of the primary economic challenges in software engineering.
The economic impact is staggering. Downtime costs for small businesses can reach £8,000/hour, while large enterprises face potential losses of £4 million/hour. Beyond financial implications, delayed bug fixes create security vulnerabilities, compromise user experience, and reduce competitive advantage. Traditional approaches relying on developer expertise and manual intervention cannot scale to meet the demands of modern distributed systems, microservices architectures, and cloud-native applications.
1.2 Evolution of Software Healing Systems
The journey toward self-healing software spans multiple domains. Infrastructure-level resilience has matured through technologies like Kubernetes self-healing pods, which automatically restart failed containers and manage workload replication. However, these solutions address infrastructure failures rather than application-level bugs. Concurrently, early automated program repair techniques like GenProg employed genetic programming to evolve code patches using test case feedback. These foundational approaches lacked semantic understanding of code intent and remained limited to specific bug patterns.
Recent advances in Large Language Models have catalyzed unprecedented progress. RepairAgent, the first autonomous LLM-based agent for program repair, demonstrates how transformer-based models can autonomously plan and execute debugging actions similar to human developers. SynergyBug combines BERT and GPT-3 to achieve 98.79% bug detection accuracy by unifying detection and repair into a single automated process. Simultaneously, biological-inspired healing frameworks reimagine software recovery by mimicking immune system principles—sensors detect damage, neural pathways relay information, and adaptive responses trigger healing.
1.3 Scope and Objectives
This survey systematically reviews self-healing software systems literature, focusing on five interconnected dimensions: 
(1) Anomaly Detection in Logs; 
(2) Autonomous Program Repair; 
(3) AI Orchestration; 
(4) Semantic Code Analysis; and 
(5) Safe Deployment and Rollback. 
The survey synthesizes findings across these dimensions to present an integrated framework. Major gaps identified include limited semantic understanding across diverse code patterns, insufficient multi-language and framework support, nascent continuous learning capabilities, and incomplete end-to-end automation pipelines.
2. Literature Review
2.1 Anomaly Detection in System Logs
2.1.1 Deep Learning Approaches for Log Analysis
Log analysis serves as the primary sensory mechanism for detecting system anomalies. Traditional rule-based approaches struggle with high-dimensional log data and cannot detect novel failure patterns. Deep learning has emerged as the dominant paradigm for automated log anomaly detection.
LSTM-Based Anomaly Detection: Long Short-Term Memory networks excel at capturing temporal dependencies in sequential log data. The architecture processes sequences of log events, where each event is encoded as an embedding. The LSTM learns normal patterns by predicting the next event in sequences; significant prediction errors indicate anomalies. Modern implementations combine LSTM models with attention mechanisms, enabling the system to focus on specific log sequences most indicative of failures.
The effectiveness of LSTM autoencoders has been empirically validated. Research comparing LSTM autoencoders, Isolation Forest, and other detection methods demonstrated that LSTM autoencoders achieved superior recall, precision, and F1 scores on standard benchmarks. The autoencoder variant learns normal log patterns during training; reconstruction loss for anomalous samples becomes significantly larger, providing a sensitive anomaly signal.
2.1.2 Isolation Forest and Ensemble Methods
The Isolation Forest algorithm provides a complementary approach, particularly effective for high-dimensional log data. Unlike distance-based anomaly detectors that require assumptions about normal data distribution, Isolation Forest isolates anomalies through random partitioning. The algorithm constructs an ensemble of isolation trees; normal points require many splits to isolate while anomalies isolate quickly.
Comparative studies reveal that Isolation Forest demonstrates lower false positive rates compared to LSTM autoencoders in complex scenarios. Ensemble approaches combining multiple detection methods leverage complementary strengths: LSTM captures temporal patterns while Isolation Forest identifies statistical outliers. These ensemble methods show improved robustness, particularly when log data exhibits distribution shift or contains previously unseen event types.
2.1.3 Semantic Log Parsing
Raw log messages must be converted into structured formats before anomaly detection. Advanced parsing techniques using Large Language Models address this challenge. AdaParser represents a state-of-the-art approach combining tree-based parsing with self-generated in-context learning. The parser achieves superior accuracy and robustness on evolving logs compared to traditional methods.
ULog provides an unsupervised LLM-based parsing framework leveraging log contrastive units—pairs of similar logs differing in specific fields. These advances in semantic log parsing ensure that anomaly detection systems receive high-quality structured input, improving overall pipeline accuracy.
2.2 Autonomous Program Repair and Bug Fixing
2.2.1 LLM-Based Autonomous Agents
RepairAgent revolutionizes automated program repair by treating large language models as autonomous agents capable of planning and executing multi-step repair strategies. The system orchestrates a toolkit resembling developer debugging practices: reading code, searching code repositories, applying patches, and executing test cases.
The architecture comprises three components: (1) LLM Agent, which autonomously decides which tools to invoke; (2) Tool Set, including purpose-built tools for program repair; and (3) Middleware, orchestrating LLM-tool communication. Evaluation on the Defects4J dataset demonstrates RepairAgent's effectiveness: it successfully repaired 164 bugs. The approach cost only 14 cents per bug under GPT-3.5 pricing.
2.2.2 Hybrid Deep Learning for Integrated Detection and Repair
SynergyBug presents an alternative architecture combining BERT and GPT-3 for integrated bug detection and repair. The framework processes bug reports through BERT's contextual embedding generation, while GPT-3 generates code fixes and explanatory text. This dual-model approach unifies traditionally separate detection and repair phases.
The system achieved 98.79% detection accuracy with 97.23% precision and 96.56% recall. Advantages of this approach include: (1) unified architecture reducing pipeline latency; (2) integrated semantic understanding bridging detection and repair; and (3) explainability through generated descriptions accompanying each fix.
2.2.3 Genetic Programming for Evolutionary Repair
GenProg pioneered automated program repair using genetic programming guided by test cases. This approach evolves program variants through mutation and crossover operations; variants passing all test cases while modifying faulty code represent candidate repairs. Genetic programming proved effective on diverse bug classes.
Strengths include generality across diverse bug patterns and robustness through population-based search. Limitations include computational expense and difficulty interpreting evolved repairs. Recent work explores reinforcement learning-guided mutation operator selection to improve efficiency.
2.3 Semantic Code Analysis and Understanding
2.3.1 Abstract Syntax Trees and Code Embeddings
Understanding code intent requires moving beyond surface-level syntax to semantic structures. Abstract Syntax Trees (ASTs) represent program structure hierarchically, abstracting away syntactic details like punctuation while preserving essential semantics. AST-based analysis enables static analysis by exposing program structure to automated inspection.
CodeBERT represents a breakthrough in code understanding through bimodal pre-training on code and natural language. The model learns dual embeddings capturing both syntactic structure and semantic relationships. CodeBERT enables downstream tasks including code search, clone detection, and defect prediction by providing rich contextual representations.
2.3.2 Control Flow and Data Flow Analysis
Understanding how execution flows through programs and how data propagates enables identifying complex bugs. Control Flow Graphs (CFGs) represent all possible execution paths; Data Dependency Graphs (DDGs) capture value dependencies between statements; Control Dependency Graphs (CDGs) indicate conditional dependencies.
Advanced diagnosis systems leverage these graph-based representations. Retrieval-Augmented Generation (RAG) models pull historical context from bug repositories and prior fixes, combining this with AST/DDG analysis to pinpoint fault locations.
2.4 Reinforcement Learning and Continuous Learning
2.4.1 RL-Driven Repair Policy Optimization
Reinforcement learning optimizes repair strategies by treating bug fixing as a sequential decision-making problem. An agent observes state (bug information, partial fixes), takes actions (code modifications), and receives rewards (test pass/fail outcomes, code quality metrics).
Process-based reinforcement learning, wherein an LLM is fine-tuned via supervised learning on expert repair trajectories and then optimized via RL feedback, shows particular promise. Results demonstrate that smaller models can achieve excellent performance through process supervision and RL, with 7–20% absolute gains on repair tasks.
2.4.2 Meta-Learning for Continuous System Adaptation
Meta-learning enables systems to improve their learning algorithms themselves. In the context of self-healing systems, meta-learning supports continuous learning: as systems encounter new bug types, they adapt without catastrophic forgetting of prior knowledge.
Automated Continual Learning (ACL) trains self-referential neural networks to meta-learn their own continual learning algorithms. La-MAML combines meta-learning with gradient-based learning rate modulation for efficient online continual learning.
2.5 CI/CD Integration, Testing, and Safe Deployment
2.5.1 Automated Testing and Deployment Pipelines
Self-healing systems must integrate seamlessly with continuous integration/continuous deployment (CI/CD) infrastructure. Automated testing validates repairs before deployment, ensuring candidate fixes don't introduce new bugs. Testing strategies include unit testing, regression testing, fuzzing, property-based testing, and mutation testing.
Deployment patterns affect safety and speed. Blue-Green deployments maintain two production-identical environments, enabling instant traffic switching when problems arise. Canary releases gradually roll out changes to subsets of users, detecting issues before full rollout.
2.5.2 Rollback Automation and Safety Mechanisms
Rollback automation detects deployment failures through monitoring metrics—error rates, response time spikes, resource consumption anomalies—and automatically reverts changes when thresholds breach. Clear rollback criteria prove essential; without predefined triggers, systems either react too slowly or trigger spurious rollbacks.
Immutable infrastructure simplifies rollback: each deployment creates entirely new infrastructure instances from pre-verified images. Versioning strategies enable precise rollback targeting. Database state management presents challenges: rollbacks may require schema migrations or data reversion.
3. Materials and Methods
3.1 System Architecture and Components
3.1.1 Monitoring and Signal Collection
The foundation of any self-healing system is comprehensive monitoring capturing system behavior across multiple dimensions. Signal collection mirrors biological nervous systems sensing environmental conditions. Modern monitoring stacks employ multiple tools including Prometheus, Datadog, OpenTelemetry, Elasticsearch/Kibana, and Grafana.
Kubernetes health check mechanisms provide infrastructure-level signals. Liveness probes detect hung processes requiring restart. Readiness probes determine service readiness to accept traffic. Startup probes delay readiness checks until application initialization completes. SLI collection measures actual performance including error rates, latency percentiles, throughput, and availability.
3.1.2 Diagnosis Module with AI Orchestration
The diagnosis module interprets signals using AI models, analogous to biological neural processing. Anomaly Detection Engine implements hybrid approaches combining LSTM autoencoders for temporal pattern recognition with Isolation Forest for statistical outlier detection.
Retrieval-Augmented Generation (RAG) Models query historical bug repositories and fix patterns, retrieving contextually similar cases. Code Understanding via AST Analysis parses Abstract Syntax Trees from identified fault locations, enabling semantic analysis of program structure. LLM-Based Diagnosis analyzes combined signals to pinpoint root causes.
3.1.3 Healing Agent and Repair Generation
The healing agent executes repair strategies, invoking appropriate repair generation methods based on diagnosis. LLM-Based Patch Generation involves autonomous agents that generate candidate patches by prompting LLMs with bug context, faulty code, and test case information.
Genetic Programming is used for optimization-based repairs, evolving code variants through guided mutation. Reinforcement Learning-Guided Repair uses RL-trained policies to decide which repair operations to apply. Multi-Language Support ensures repair systems handle diverse languages through language-specific AST parsers.
3.1.4 Verification and Sandbox Testing
Before deployment, repairs undergo rigorous validation including: Compilation/Syntax Checking to verify generated code is syntactically correct, Unit Testing running existing test suites against repairs, Mutation Testing injecting artificial faults to verify test quality, Sandbox Execution running repaired code in isolated environments, Regression Analysis comparing behavior before/after repair, and Property-Based Testing exploring edge cases.
3.1.5 CI/CD Pipeline Integration
Verified repairs enter the deployment pipeline with automated gates. Policy-Based Gates enforce different policies based on organizational needs. Gradual Rollout uses blue-green or canary deployment patterns. Automatic Rollback detects post-deployment anomalies and triggers reversion. Feedback Loop captures deployment outcomes for the learning system.
3.2 Anomaly Detection Methodology
3.2.1 LSTM Autoencoder Implementation
LSTM autoencoders learn normal patterns from historical logs. Training Phase: Pre-process logs into fixed-length sequences, embed each log event using fastText or Word2Vec, encode sequences using bidirectional LSTM to generate compressed representations, decode compressed representations back to original dimensions, minimize reconstruction loss on normal log sequences.
Inference Phase: Process incoming log sequences through trained autoencoder, calculate reconstruction error, flag sequences with error exceeding threshold as anomalies. Hyperparameters requiring tuning include sequence length, embedding dimension, LSTM hidden units, and threshold for anomaly flagging.
3.2.2 Isolation Forest Implementation
Isolation Forest constructs an ensemble of random isolation trees. Algorithm: Sub-sample dataset and recursively partition via random feature/threshold selection; aggregate isolation depth across forest where shorter paths indicate anomalies; score samples based on normalized path length; flag samples exceeding contamination parameter as anomalies.
Advantages include handling high-dimensional data, robustness to irrelevant features, and computational efficiency. Disadvantages include potential struggles with complex dependencies compared to LSTM approaches.
3.2.3 Semantic Log Parsing with AdaParser
Log parsing extracts structured templates from raw messages. Process: Group similar logs via tree-based clustering; use LLM with self-generated in-context examples to parse grouped logs; apply template correction mechanisms for variable identification; refine through multi-iteration self-correction. Result: Raw logs transformed to (EventID, Template, ParameterList) tuples enabling downstream analysis.
3.3 Automated Program Repair Methodology
3.3.1 RepairAgent-Style Autonomous Repair
Multi-step autonomous repair process: Problem Understanding extracts bug symptoms from traces and reproduces failures; Information Gathering reads relevant code sections and searches repositories; Hypothesis Formation generates initial repair hypotheses; Candidate Generation synthesizes code modifications using LLM; Validation executes test cases; Refinement gathers additional context if tests fail; Deployment packages successful repairs.
Tool set supporting these steps includes: read_code, search_repository, apply_patch, run_tests, execute_verification, retrieve_similar_fixes, analyze_error_trace, and extract_code_semantics.
3.3.2 Genetic Programming Approach
For optimization-based repairs: Fault Localization identifies program locations most likely to contain bugs; Representation represents candidate programs as genotypes (code edit operations); Fitness Evaluation executes against test suite, measuring fitness; Evolution applies mutation, crossover, selection based on fitness; Termination stops when candidate passes tests or budget exhausted; Minimization reduces evolved repairs to minimal changes.
3.3.3 Reinforcement Learning-Guided Repair
Policy learning for repair action selection: State Representation encodes bug information and repair progress; Action Space defines repair operations; Reward Design creates success metrics; Policy Optimization fine-tunes LLM via supervised learning then RL; Inference samples repair actions from learned policy. Challenges include avoiding reward hacking, generalizing across diverse bug types, and designing interpretable reward functions.
4. Projected Results
4.1 Expected Performance Metrics
Anomaly Detection Accuracy: Systems combining LSTM and Isolation Forest should achieve >95% detection accuracy, approaching the ~98% rates demonstrated in SynergyBug. F1 scores >0.92 are realistic given state-of-the-art methods.
Repair Success Rates: On standard benchmarks (Defects4J, GitBug-Java), autonomous repair systems should repair 15–20% of bugs, approaching RepairAgent's 164/835 success rate (19.6%). Performance varies significantly by bug class: semantic bugs fix more readily than non-deterministic failures.
Cost Metrics: LLM-based repair costs ~$0.14–0.50 per bug under current pricing. Total cost-per-repair includes monitoring infrastructure (~$0.10–50/month for small-to-medium deployments), storage for logs/models (~$50–500/month), and LLM inference costs.
Latency Metrics: End-to-end repair cycles (detection→diagnosis→repair→verification→deployment) should complete within hours for most bugs. Anomaly detection should trigger within seconds of failure manifestation. False positive rates should remain <5% to avoid alert fatigue.
4.2 Scalability Projections
System Scale: Production deployments handling thousands of services and petabytes of log data supporting millions of users should be achievable through distributed monitoring and repair agents.
Repair Complexity: Current systems effectively handle single-file, single-function bugs (<10 lines). Multi-file repairs and complex architectural refactoring remain challenging; projection: 5–10 years for widespread multi-file repair capability.
Language Coverage: Initial deployments target Python, Java, C++ (top enterprise languages). Expansion to JavaScript, Go, Rust feasible within 12–24 months.
4.3 Economic Impact Projections
Maintenance Cost Reduction: Automating 20–30% of routine bug fixes could reduce maintenance costs by $14–21 billion annually in the US. Organizations adopting self-healing systems should see 15–25% maintenance cost reductions within 2–3 years.
Downtime Reduction: Median downtime per incident could decrease from hours to minutes through automated detection and repair. Developer Productivity: Freed from routine debugging, developers allocate time to architecture, feature development, and testing—higher-value activities.
5. Conclusion
Self-healing software systems represent a transformative evolution in software maintenance, transitioning from reactive manual debugging to proactive autonomous repair. This survey synthesizes the state-of-the-art across interconnected domains: deep learning-based anomaly detection in logs, LLM-driven autonomous program repair agents, semantic code analysis, reinforcement learning for policy optimization, and safe CI/CD deployment.
Key findings reveal that integrated systems combining multiple repair techniques, robust anomaly detection, semantic code understanding, and careful safety mechanisms demonstrate superior performance to single-method approaches. RepairAgent's 19.6% repair success rate and SynergyBug's 98.79% detection accuracy demonstrate feasibility.
Critical research gaps include: 
(1) Semantic Understanding - current systems struggle with non-obvious bugs requiring deep understanding of program intent; 
(2) Generalization - models trained on specific datasets often fail on diverse real-world code; 
(3) Accountability - when autonomous systems make repairs, responsibility for failures remains ambiguous; 
(4) Scalability - deploying systems across heterogeneous legacy infrastructure presents integration challenges.
Future directions should prioritize: 
(1) Explainability - developing repair systems that justify their actions, building trust; 
(2) Continuous Learning - implementing robust meta-learning approaches enabling adaptation; 
(3) Human-AI Collaboration - creating interfaces enabling developers to guide and validate repairs; 
(4) Standardization - establishing benchmarks enabling fair comparison.
The convergence of advances in large language models, deep learning, reinforcement learning, and cloud-native infrastructure creates unprecedented opportunity. Organizations investing in self-healing systems today will realize competitive advantages through reduced maintenance costs, improved reliability, and accelerated development velocity.
6. Acknowledgements
We acknowledge the foundational contributions of researchers at UC Davis, University of Stuttgart, and industrial practitioners who pioneered autonomous program repair and self-healing system architectures. Special recognition to the open-source communities developing critical infrastructure tools: Prometheus, Grafana, Kubernetes, and OpenTelemetry, which enable practical implementation of self-healing systems. We thank the developers and researchers maintaining Defects4J and related benchmark datasets that enable rigorous evaluation of repair techniques.
7. References
[1] Bouzenia, I., Devanbu, P., & Pradel, M. (2025). "RepairAgent: An Autonomous, LLM-Based Agent for Program Repair." In Proceedings of the International Conference on Software Engineering, Stuttgart, Germany.

[2] Chen, H. (2025). "SynergyBug: A deep learning approach to autonomous debugging and code remediation." Scientific Reports, 15(1), 24888. Nature Publishing Group.

[3] Hokstad Consulting. (2025). "Rollback Automation: Best Practices for CI/CD." Retrieved from https://hokstadconsulting.com/blog/rollback-automation-best-practices-for-cicd

[4] Baqar, M., Khanda, R., & Naqvi, S. (2024). "Self-Healing Software Systems: Lessons from Nature, Powered by AI." arXiv preprint arXiv:2504.20093.
[5] Le Goues, C., Nguyen, T., Forrest, S., & Weimer, W. (2011). "GenProg: A generic method for automatic software repair." ACM Transactions on Software Engineering and Methodology, 22(3), 1-45.

[6] Bouzenia, I., Devanbu, P., & Pradel, M. (2024). "An Autonomous, LLM-Based Agent for Program Repair." arXiv preprint arXiv:2403.17134, 178(1), 1-18.

[7] Chen, Z., Kommrusch, S., Tufano, M., Pouchet, L. N., Poshyvanyk, D., & Monperrus, M. (2021). "Deep learning-based system log analysis for anomaly detection." ACM Transactions on Software Engineering and Methodology, 30(4), 1-32.

[8] Baqar, M., Khanda, R., & Naqvi, S. (2025). "Self-Healing Software Systems: Lessons from Nature, Powered by AI." arXiv preprint arXiv:2504.20093.

[9] KTH Royal Institute. (2021). "Anomaly Detection for Insider Threats." LSTM Autoencoder vs Isolation Forest Comparison. Retrieved from https://kth.diva-portal.org/smash/get/diva2:1868197

[10] Zhu, S., Karpovich, A., Chen, A., Koscheka, J., Wen, D., Zhu, Y., & Geramifard, A. (2025). "Agentic Reinforcement Learning for Real-World Code Repair." arXiv preprint arXiv:2510.22075.
