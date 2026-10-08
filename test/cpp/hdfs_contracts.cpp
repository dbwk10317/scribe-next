// Bounded JNI local-filesystem probe for the actual HdfsFile class (original plus
// the scribe-next modifications listed at the top of src/HdfsFile.cpp).
#include "common.h"
#include "file.h"
#include "HdfsFile.h"
#include <algorithm>
#include <fstream>
#include <iterator>

static void require(bool value,const char* message) {
  if (!value) throw std::runtime_error(message);
}
static std::string bytes(const std::string& path) {
  std::ifstream stream(path.c_str(),std::ios::binary);
  return std::string(std::istreambuf_iterator<char>(stream),std::istreambuf_iterator<char>());
}
int main(int argc,char** argv) {
  alarm(20);
  if (argc!=2) return 2;
  try {
    const std::string root(argv[1]),path=root+"/data",marker=root+"/current";
    const std::string first("A\0B\n\xff",5),second("tail");
    HdfsFile file(path);
    require(file.createDirectory(root),"directory contract failed");
    require(file.openWrite()&&file.write(first),"initial write failed");
    file.flush();require(file.fileSize()==first.size(),"initial size differs");file.close();
    require(bytes(path)==first,"initial bytes differ");
    require(file.openWrite()&&file.write(second),"append failed");file.flush();file.close();
    require(bytes(path)==first+second,"append bytes differ");
    require(file.openRead(),"openRead failed");
    std::string ignored("unchanged");require(file.readNext(ignored)==-1000000000L&&ignored=="unchanged","original unsupported readNext changed");
    require(file.getFrame(5).empty(),"original unframed contract changed");file.close();
    require(file.openTruncate()&&file.write("Z"),"truncate failed");file.flush();file.close();
    require(bytes(path)==first+second+"Z","closed-handle truncate append behavior changed");
    HdfsFile connected(path);
    require(connected.openTruncate()&&connected.write("Z"),"connected truncate failed");
    connected.flush();connected.close();
    require(bytes(path)=="Z","connected truncate did not replace contents");
    require(file.createSymlink("data",marker),"regular marker creation failed");
    require(bytes(marker)=="data","regular marker contents differ");
    std::vector<std::string> listed=FileInterface::list(root,"hdfs");std::sort(listed.begin(),listed.end());
    require(listed==std::vector<std::string>({"current","data"}),"directory inventory differs");
    HdfsFile deletion(path);deletion.deleteFile();deletion.close();
    require(access(path.c_str(),F_OK)!=0,"delete did not remove file");
    std::cout<<"hdfs JNI local bytes/append/truncate/marker/list/delete PASS\n";
    return 0;
  } catch(const std::exception& error) {std::cerr<<error.what()<<"\n";return 1;}
}
