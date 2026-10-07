// Fixture for actual ConnPool methods with deterministic connection stubs.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "common.h"
#include "conn_pool.h"
#include <thread>
#include <mutex>
#include <condition_variable>
#include <chrono>
static std::mutex state;
static std::condition_variable changed;
static bool sending=false,release_send=false,reopen_event=false,reopened=false,unsafe_open=false,wrong_unlock=false;
static thread_local bool opener=false;
static bool throw_send=false;
static std::map<scribeConn*,std::thread::id> owners;
static std::map<scribeConn*,bool> opened;
scribeConn::scribeConn(const std::string&,unsigned long,int):refCount(1){pthread_mutexattr_t a;pthread_mutexattr_init(&a);pthread_mutexattr_settype(&a,PTHREAD_MUTEX_ERRORCHECK);pthread_mutex_init(&mutex,&a);pthread_mutexattr_destroy(&a);{std::lock_guard<std::mutex> g(state);opened[this]=false;}}
scribeConn::scribeConn(const std::string&,const server_vector_t&,int):refCount(1){pthread_mutex_init(&mutex,nullptr);{std::lock_guard<std::mutex> g(state);opened[this]=false;}}
scribeConn::~scribeConn(){pthread_mutex_destroy(&mutex);}
void scribeConn::addRef(){++refCount;} void scribeConn::releaseRef(){--refCount;} unsigned scribeConn::getRef(){return refCount;} void scribeConn::setRef(unsigned n){refCount=n;}
void scribeConn::lock(){if(opener){std::lock_guard<std::mutex> g(state);reopen_event=true;changed.notify_all();}pthread_mutex_lock(&mutex);std::lock_guard<std::mutex> g(state);owners[this]=std::this_thread::get_id();}
void scribeConn::unlock(){std::lock_guard<std::mutex> g(state);if(owners[this]!=std::this_thread::get_id())wrong_unlock=true;owners[this]=std::thread::id();pthread_mutex_unlock(&mutex);}
bool scribeConn::isOpen(){std::lock_guard<std::mutex> g(state);if(opener){unsafe_open=owners[this]!=std::this_thread::get_id();reopen_event=true;changed.notify_all();}return opened[this];}
bool scribeConn::open(){std::lock_guard<std::mutex> g(state);opened[this]=true;return true;}
void scribeConn::close(){std::lock_guard<std::mutex> g(state);opened[this]=false;}
int scribeConn::send(boost::shared_ptr<logentry_vector_t>){if(throw_send)throw std::runtime_error("fixture send allocation failure");std::unique_lock<std::mutex> g(state);opened[this]=false;sending=true;changed.notify_all();if(!changed.wait_for(g,std::chrono::seconds(3),[]{return release_send;}))std::abort();return CONN_TRANSIENT;}
class TestPool:public ConnPool{public:void seed(boost::shared_ptr<scribeConn> c){connMap["fixture:1"]=c;} unsigned refs(){return connMap.at("fixture:1")->getRef();} bool empty(){return connMap.empty();}};
int main(int argc,char** argv){
 TestPool pool;boost::shared_ptr<scribeConn> old(new scribeConn("fixture",1,1));pool.seed(old);
 boost::shared_ptr<logentry_vector_t> messages(new logentry_vector_t);
 if(argc==2 && std::string(argv[1])=="exception") {
  throw_send=true;try {pool.send("fixture",1,messages);return 2;}catch(const std::runtime_error&){}
  if(!pool.open("fixture",1,1) || pool.refs()!=2)return 3;
  pool.close("fixture",1);pool.close("fixture",1);
  std::cout<<"PASS exception"<<std::endl;return pool.empty()?0:4;
 }
 int result=-99;std::thread sender([&]{result=pool.send("fixture",1,messages);});
 {std::unique_lock<std::mutex> g(state);if(!changed.wait_for(g,std::chrono::seconds(3),[]{return sending;}))std::abort();}
 std::thread reopener([&]{opener=true;bool success=pool.open("fixture",1,1);{std::lock_guard<std::mutex> g(state);reopened=success;changed.notify_all();}});
 {std::unique_lock<std::mutex> g(state);if(!changed.wait_for(g,std::chrono::seconds(3),[]{return reopen_event;}))std::abort();if(unsafe_open && !changed.wait_for(g,std::chrono::seconds(3),[]{return reopened;}))std::abort();release_send=true;changed.notify_all();}
 sender.join();reopener.join();bool bad=unsafe_open||wrong_unlock;
 if(bad)old->unlock();
 if(result!=CONN_TRANSIENT || pool.refs()!=2)bad=true;
 pool.close("fixture",1);if(pool.refs()!=1)bad=true;pool.close("fixture",1);if(!pool.empty())bad=true;
 std::cout<<"unsafe_isOpen="<<unsafe_open<<" wrong_unlock="<<wrong_unlock<<" refcount/key_preserved="<<!bad<<std::endl;return bad?1:0;
}
