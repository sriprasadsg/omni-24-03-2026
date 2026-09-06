use yara_x::{Compiler, Rules, Scanner};

pub struct YaraEngine {
    rules: Rules,
}

impl YaraEngine {
    pub fn new(rule_source: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let mut compiler = Compiler::new();
        compiler.add_source(rule_source)?;
        let rules = compiler.build();
        Ok(Self { rules })
    }

    pub fn scan(&self, data: &[u8]) -> Vec<String> {
        let mut scanner = Scanner::new(&self.rules);
        let results = scanner.scan(data).unwrap();
        results.matching_rules()
            .map(|r| r.identifier().to_string())
            .collect()
    }
}
