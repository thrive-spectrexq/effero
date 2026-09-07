//! A minimal, dependency-free, safe expression evaluator for rule
//! conditions.
//!
//! Conditions are simple boolean expressions over named numeric/boolean
//! facts (see `crate::policy::Rule::condition`), e.g.:
//!
//!   "nearest_person_distance_m < 1.0"
//!   "time_hour >= 23 || time_hour < 6"
//!   "person_detected && nearest_person_distance_m < 2.0"
//!
//! This is hand-rolled rather than pulled in from a general-purpose
//! expression-evaluation crate on purpose: the safety kernel's entire job
//! is being small enough to audit by reading it, and a ~150-line
//! recursive-descent parser over a five-token grammar is easier to
//! fully verify than a general-purpose expression library's surface
//! area. It can never execute arbitrary code -- a malformed or hostile
//! policy file can at worst produce a wrong *decision* (and this module
//! always fails toward `false`, i.e. toward requiring the caller's
//! default/approval path), never arbitrary behavior.

use std::collections::HashMap;
use std::iter::Peekable;
use std::str::Chars;

pub type Facts = HashMap<String, Fact>;

#[derive(Debug, Clone, Copy)]
pub enum Fact {
    Number(f64),
    Bool(bool),
}

/// Evaluate `condition` against `facts`. Fails *safe*: any parse or
/// evaluation error results in `false`, so a broken condition string can
/// never accidentally grant an action it wasn't clearly written to grant.
pub fn evaluate(condition: &str, facts: &Facts) -> bool {
    if condition.trim() == "true" {
        return true;
    }

    match Parser::new(condition).parse_expr() {
        Ok(expr) => expr.eval(facts).unwrap_or(false),
        Err(_) => false,
    }
}

// ---------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
enum Token {
    Ident(String),
    Number(f64),
    True,
    False,
    And,
    Or,
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
    LParen,
    RParen,
}

struct Lexer<'a> {
    chars: Peekable<Chars<'a>>,
}

impl<'a> Lexer<'a> {
    fn new(input: &'a str) -> Self {
        Self { chars: input.chars().peekable() }
    }

    fn tokenize(mut self) -> Result<Vec<Token>, String> {
        let mut tokens = Vec::new();
        while let Some(&c) = self.chars.peek() {
            match c {
                c if c.is_whitespace() => {
                    self.chars.next();
                }
                '(' => {
                    self.chars.next();
                    tokens.push(Token::LParen);
                }
                ')' => {
                    self.chars.next();
                    tokens.push(Token::RParen);
                }
                '&' => {
                    self.chars.next();
                    if self.chars.next() != Some('&') {
                        return Err("expected '&&'".into());
                    }
                    tokens.push(Token::And);
                }
                '|' => {
                    self.chars.next();
                    if self.chars.next() != Some('|') {
                        return Err("expected '||'".into());
                    }
                    tokens.push(Token::Or);
                }
                '<' => {
                    self.chars.next();
                    if self.chars.peek() == Some(&'=') {
                        self.chars.next();
                        tokens.push(Token::Le);
                    } else {
                        tokens.push(Token::Lt);
                    }
                }
                '>' => {
                    self.chars.next();
                    if self.chars.peek() == Some(&'=') {
                        self.chars.next();
                        tokens.push(Token::Ge);
                    } else {
                        tokens.push(Token::Gt);
                    }
                }
                '=' => {
                    self.chars.next();
                    if self.chars.next() != Some('=') {
                        return Err("expected '=='".into());
                    }
                    tokens.push(Token::Eq);
                }
                '!' => {
                    self.chars.next();
                    if self.chars.next() != Some('=') {
                        return Err("expected '!='".into());
                    }
                    tokens.push(Token::Ne);
                }
                c if c.is_ascii_digit() || c == '-' || c == '.' => {
                    let mut buf = String::new();
                    buf.push(c);
                    self.chars.next();
                    while let Some(&d) = self.chars.peek() {
                        if d.is_ascii_digit() || d == '.' {
                            buf.push(d);
                            self.chars.next();
                        } else {
                            break;
                        }
                    }
                    let n: f64 = buf.parse().map_err(|_| format!("bad number: {buf}"))?;
                    tokens.push(Token::Number(n));
                }
                c if c.is_alphabetic() || c == '_' => {
                    let mut buf = String::new();
                    buf.push(c);
                    self.chars.next();
                    while let Some(&d) = self.chars.peek() {
                        if d.is_alphanumeric() || d == '_' {
                            buf.push(d);
                            self.chars.next();
                        } else {
                            break;
                        }
                    }
                    match buf.as_str() {
                        "true" => tokens.push(Token::True),
                        "false" => tokens.push(Token::False),
                        _ => tokens.push(Token::Ident(buf)),
                    }
                }
                other => return Err(format!("unexpected character: {other}")),
            }
        }
        Ok(tokens)
    }
}

// ---------------------------------------------------------------------
// AST + recursive-descent parser
// ---------------------------------------------------------------------

enum Expr {
    Bool(bool),
    Ident(String),
    Compare(String, CmpOp, f64),
    And(Box<Expr>, Box<Expr>),
    Or(Box<Expr>, Box<Expr>),
}

#[derive(Clone, Copy)]
enum CmpOp {
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
}

impl Expr {
    fn eval(&self, facts: &Facts) -> Result<bool, ()> {
        match self {
            Expr::Bool(b) => Ok(*b),
            Expr::Ident(name) => match facts.get(name) {
                Some(Fact::Bool(b)) => Ok(*b),
                _ => Ok(false), // missing/wrong-typed fact fails safe to false
            },
            Expr::Compare(name, op, rhs) => {
                let lhs = match facts.get(name) {
                    Some(Fact::Number(n)) => *n,
                    _ => return Ok(false), // missing/wrong-typed fact fails safe to false
                };
                Ok(match op {
                    CmpOp::Lt => lhs < *rhs,
                    CmpOp::Le => lhs <= *rhs,
                    CmpOp::Gt => lhs > *rhs,
                    CmpOp::Ge => lhs >= *rhs,
                    CmpOp::Eq => (lhs - rhs).abs() < f64::EPSILON,
                    CmpOp::Ne => (lhs - rhs).abs() >= f64::EPSILON,
                })
            }
            Expr::And(l, r) => Ok(l.eval(facts)? && r.eval(facts)?),
            Expr::Or(l, r) => Ok(l.eval(facts)? || r.eval(facts)?),
        }
    }
}

struct Parser {
    tokens: Vec<Token>,
    pos: usize,
}

impl Parser {
    fn new(input: &str) -> Self {
        // tokenize() errors are surfaced later as a parse failure via an
        // empty token stream, which `parse_expr` below turns into `Err`.
        let tokens = Lexer::new(input).tokenize().unwrap_or_default();
        Self { tokens, pos: 0 }
    }

    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.pos)
    }

    fn next(&mut self) -> Option<Token> {
        let t = self.tokens.get(self.pos).cloned();
        self.pos += 1;
        t
    }

    fn parse_expr(&mut self) -> Result<Expr, String> {
        if self.tokens.is_empty() {
            return Err("empty or unparseable condition".into());
        }
        let expr = self.parse_or()?;
        if self.pos != self.tokens.len() {
            return Err("trailing tokens after expression".into());
        }
        Ok(expr)
    }

    fn parse_or(&mut self) -> Result<Expr, String> {
        let mut lhs = self.parse_and()?;
        while matches!(self.peek(), Some(Token::Or)) {
            self.next();
            let rhs = self.parse_and()?;
            lhs = Expr::Or(Box::new(lhs), Box::new(rhs));
        }
        Ok(lhs)
    }

    fn parse_and(&mut self) -> Result<Expr, String> {
        let mut lhs = self.parse_atom()?;
        while matches!(self.peek(), Some(Token::And)) {
            self.next();
            let rhs = self.parse_atom()?;
            lhs = Expr::And(Box::new(lhs), Box::new(rhs));
        }
        Ok(lhs)
    }

    fn parse_atom(&mut self) -> Result<Expr, String> {
        match self.next() {
            Some(Token::True) => Ok(Expr::Bool(true)),
            Some(Token::False) => Ok(Expr::Bool(false)),
            Some(Token::LParen) => {
                let inner = self.parse_or()?;
                match self.next() {
                    Some(Token::RParen) => Ok(inner),
                    _ => Err("expected ')'".into()),
                }
            }
            Some(Token::Ident(name)) => {
                // Either a bare boolean fact, or the left-hand side of a comparison.
                match self.peek() {
                    Some(Token::Lt | Token::Le | Token::Gt | Token::Ge | Token::Eq | Token::Ne) => {
                        let op = match self.next().unwrap() {
                            Token::Lt => CmpOp::Lt,
                            Token::Le => CmpOp::Le,
                            Token::Gt => CmpOp::Gt,
                            Token::Ge => CmpOp::Ge,
                            Token::Eq => CmpOp::Eq,
                            Token::Ne => CmpOp::Ne,
                            _ => unreachable!(),
                        };
                        match self.next() {
                            Some(Token::Number(n)) => Ok(Expr::Compare(name, op, n)),
                            _ => Err("expected a number after comparison operator".into()),
                        }
                    }
                    _ => Ok(Expr::Ident(name)),
                }
            }
            other => Err(format!("unexpected token: {other:?}")),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bare_true_always_matches() {
        assert!(evaluate("true", &Facts::new()));
    }

    #[test]
    fn simple_numeric_comparison() {
        let mut facts = Facts::new();
        facts.insert("nearest_person_distance_m".to_string(), Fact::Number(0.5));
        assert!(evaluate("nearest_person_distance_m < 1.0", &facts));
        assert!(!evaluate("nearest_person_distance_m >= 1.0", &facts));
    }

    #[test]
    fn compound_boolean_expression() {
        let mut facts = Facts::new();
        facts.insert("time_hour".to_string(), Fact::Number(23.0));
        assert!(evaluate("time_hour >= 23 || time_hour < 6", &facts));

        facts.insert("time_hour".to_string(), Fact::Number(14.0));
        assert!(!evaluate("time_hour >= 23 || time_hour < 6", &facts));
    }

    #[test]
    fn and_and_bare_bool_fact() {
        let mut facts = Facts::new();
        facts.insert("person_detected".to_string(), Fact::Bool(true));
        facts.insert("nearest_person_distance_m".to_string(), Fact::Number(0.8));
        assert!(evaluate("person_detected && nearest_person_distance_m < 2.0", &facts));

        facts.insert("person_detected".to_string(), Fact::Bool(false));
        assert!(!evaluate("person_detected && nearest_person_distance_m < 2.0", &facts));
    }

    #[test]
    fn parenthesized_expression() {
        let mut facts = Facts::new();
        facts.insert("a".to_string(), Fact::Number(1.0));
        facts.insert("b".to_string(), Fact::Number(0.0));
        assert!(evaluate("(a > 0 || b > 0) && a < 10", &facts));
    }

    #[test]
    fn unknown_fact_fails_safe_to_false() {
        let facts = Facts::new();
        assert!(!evaluate("undefined_fact > 1.0", &facts));
    }

    #[test]
    fn malformed_condition_fails_safe_to_false() {
        let facts = Facts::new();
        assert!(!evaluate("this is not >< valid ((", &facts));
    }
}
