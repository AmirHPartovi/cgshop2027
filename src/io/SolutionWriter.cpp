#include "SolutionWriter.h"
#include "utils/Logger.h"
#include <filesystem>
#include <fstream>
#include <stdexcept>
namespace cgshop2027 {
void SolutionWriter::write(const Solution& s,const std::string& f) {
 LogScope scope("writer", "write solution");
 Logger::instance().info("writer", "writing output=" + f +
                                      " tours=" + std::to_string(s.tours.size()));
 const std::filesystem::path outputPath(f);
 const auto parent = outputPath.parent_path();
 if (!parent.empty() && parent != ".") {
   std::filesystem::create_directories(parent);
 }
 std::ofstream out(f); if(!out) throw std::runtime_error("cannot open "+f);
 out<<"{\n  \"content_type\": \""<<s.contentType<<"\",\n  \"instance_uid\": \""<<s.instanceUid<<"\",\n  \"tours\": [\n";
 for(size_t i=0;i<s.tours.size();++i){const auto& t=s.tours[i];out<<"    {\"x\": [";for(size_t j=0;j<t.points.size();++j)out<<(j?",":"")<<t.points[j].x;out<<"], \"y\": [";for(size_t j=0;j<t.points.size();++j)out<<(j?",":"")<<t.points[j].y;out<<"]}"<<(i+1<s.tours.size()?",":"")<<"\n";}
 out<<"  ],\n  \"meta\": {";size_t n=0;for(const auto& kv:s.meta)out<<(n++?",":"")<<"\""<<kv.first<<"\": \""<<kv.second<<"\"";out<<"}\n}\n";
 Logger::instance().info("writer", "solution write complete output=" + f);
}
}
