#pragma once
#include <cctype>
#include <cstring>
#include <fstream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
namespace cgshop2027::json {
struct Value {
  enum Type{NUL,BOOL,NUMBER,STRING,ARRAY,OBJECT} type=NUL; double number=0; bool boolean=false; std::string string;
  std::vector<Value> array; std::map<std::string,Value> object;
  const Value& at(const std::string& k) const { auto i=object.find(k); if(i==object.end()) throw std::runtime_error("missing JSON key: "+k); return i->second; }
};
class Parser {
  const std::string& s; size_t i=0;
  void ws(){while(i<s.size()&&std::isspace(static_cast<unsigned char>(s[i])))++i;}
  Value val(){ws(); if(i>=s.size()) throw std::runtime_error("unexpected end of JSON"); if(s[i]=='{')return obj(); if(s[i]=='[')return arr(); if(s[i]=='"')return str(); if(s.compare(i,4,"true")==0){i+=4;Value v;v.type=Value::BOOL;v.boolean=true;return v;} if(s.compare(i,5,"false")==0){i+=5;Value v;v.type=Value::BOOL;return v;} if(s.compare(i,4,"null")==0){i+=4;return {};} Value v;v.type=Value::NUMBER;size_t n=i;while(i<s.size()&&std::strchr("-+.eE0123456789",s[i]))++i;v.number=std::stod(s.substr(n,i-n));return v;}
  Value str(){Value v;v.type=Value::STRING;++i;while(i<s.size()&&s[i]!='"'){if(s[i]=='\\'&&i+1<s.size())++i;v.string+=s[i++];}if(i==s.size())throw std::runtime_error("unterminated string");++i;return v;}
  Value arr(){Value v;v.type=Value::ARRAY;++i;ws();if(i<s.size()&&s[i]==']'){++i;return v;}for(;;){v.array.push_back(val());ws();if(i>=s.size())throw std::runtime_error("unterminated array");if(s[i++]==']')return v;}}
  Value obj(){Value v;v.type=Value::OBJECT;++i;ws();if(i<s.size()&&s[i]=='}'){++i;return v;}for(;;){ws();auto k=str().string;ws();if(i>=s.size()||s[i++]!=':')throw std::runtime_error("expected colon");v.object[k]=val();ws();if(i>=s.size())throw std::runtime_error("unterminated object");if(s[i++]=='}')return v;}}
public: explicit Parser(const std::string& x):s(x){} Value parse(){auto v=val();ws();if(i!=s.size())throw std::runtime_error("trailing JSON");return v;}
};
inline Value parseFile(const std::string& f){std::ifstream in(f);if(!in)throw std::runtime_error("cannot open "+f);return Parser(std::string((std::istreambuf_iterator<char>(in)),{})).parse();}
}
