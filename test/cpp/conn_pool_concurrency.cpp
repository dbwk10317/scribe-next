// Fixture for actual ConnPool methods with deterministic connection stubs.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "common.h"
#include "conn_pool.h"
#include "context.h"
#include <thread>
#include <mutex>
#include <condition_variable>
#include <chrono>
static std::mutex state;
static std::condition_variable changed;
static bool sending=false,release_send=false,reopen_event=false,reopened=false,unsafe_open=false,wrong_unlock=false;
static thread_local bool opener=false;
static bool throw_send=false,wrong_context=false,lock_error=false;
// The pool must hand its own context to every connection it creates.
struct FixtureContext:ScribeContext{void incCounter(std::string,std::string)override{} void incCounter(std::string,std::string,long)override{} void incCounter(std::string)override{} void incCounter(std::string,long)override{}
 unsigned long long getMaxQueueSize()override{return 0;} int getThriftMaxFrameSize()const override{return 0;} int getThriftMaxMessageSize()const override{return 0;} bool hasValidThriftLimits()const override{return false;}
 ConnPool& getConnPool()override{std::abort();} facebook::fb303::FacebookBase* getFacebookBase()override{return nullptr;}};
static FixtureContext context;
static std::map<scribeConn*,std::thread::id> owners;
static std::map<scribeConn*,bool> opened;
scribeConn::scribeConn(ScribeContext& c,const std::string&,unsigned long,int):context(c),refCount(1){if(&c!=&::context)wrong_context=true;pthread_mutexattr_t a;pthread_mutexattr_init(&a);pthread_mutexattr_settype(&a,PTHREAD_MUTEX_ERRORCHECK);pthread_mutex_init(&mutex,&a);pthread_mutexattr_destroy(&a);{std::lock_guard<std::mutex> g(state);opened[this]=false;}}
scribeConn::scribeConn(ScribeContext& c,const std::string&,const server_vector_t&,int):context(c),refCount(1){if(&c!=&::context)wrong_context=true;pthread_mutex_init(&mutex,nullptr);{std::lock_guard<std::mutex> g(state);opened[this]=false;}}
scribeConn::~scribeConn(){pthread_mutex_destroy(&mutex);}
void scribeConn::addRef(){++refCount;} void scribeConn::releaseRef(){--refCount;} unsigned scribeConn::getRef(){return refCount;} void scribeConn::setRef(unsigned n){refCount=n;}
// The host/port mutex is ERRORCHECK: relocking one this thread never unlocked returns EDEADLK.
void scribeConn::lock(){if(opener){std::lock_guard<std::mutex> g(state);reopen_event=true;changed.notify_all();}const int locked=pthread_mutex_lock(&mutex);std::lock_guard<std::mutex> g(state);if(locked)lock_error=true;owners[this]=std::this_thread::get_id();}
void scribeConn::unlock(){std::lock_guard<std::mutex> g(state);if(owners[this]!=std::this_thread::get_id())wrong_unlock=true;owners[this]=std::thread::id();pthread_mutex_unlock(&mutex);}
bool scribeConn::isOpen(){std::lock_guard<std::mutex> g(state);if(opener){unsafe_open=owners[this]!=std::this_thread::get_id();reopen_event=true;changed.notify_all();}return opened[this];}
bool scribeConn::open(){std::lock_guard<std::mutex> g(state);opened[this]=true;return true;}
void scribeConn::close(){std::lock_guard<std::mutex> g(state);opened[this]=false;}
int scribeConn::send(std::shared_ptr<logentry_vector_t>){if(throw_send)throw std::runtime_error("fixture send allocation failure");std::unique_lock<std::mutex> g(state);opened[this]=false;sending=true;changed.notify_all();if(!changed.wait_for(g,std::chrono::seconds(3),[]{return release_send;}))std::abort();return CONN_TRANSIENT;}
class TestPool:public ConnPool{public:using ConnPool::ConnPool;void seed(std::shared_ptr<scribeConn> c){connMap["fixture:1"]=c;} unsigned refs(){return connMap.at("fixture:1")->getRef();} bool empty(){return connMap.empty();}};
int main(int argc,char** argv){
 TestPool pool(context);std::shared_ptr<scribeConn> old(new scribeConn(context,"fixture",1,1));pool.seed(old);
 std::shared_ptr<logentry_vector_t> messages(new logentry_vector_t);
 if(argc==2 && std::string(argv[1])=="liveness") {
  // A send whose peer never replies holds fixture:1's connection lock and a reopen of that key
  // waits for it. Neither may hold the pool map lock meanwhile: opening another key must not
  // wait for the send (bounded here at 1 s; the send stub is released afterwards either way).
  std::thread sender([&]{pool.send("fixture",1,messages);});
  {std::unique_lock<std::mutex> g(state);if(!changed.wait_for(g,std::chrono::seconds(3),[]{return sending;}))std::abort();}
  std::thread reopener([&]{opener=true;pool.open("fixture",1,1);});
  {std::unique_lock<std::mutex> g(state);if(!changed.wait_for(g,std::chrono::seconds(3),[]{return reopen_event;}))std::abort();}
  bool other_done=false,fast=false;
  std::thread other([&]{const bool ok=pool.open("other",2,1);std::lock_guard<std::mutex> g(state);other_done=ok;changed.notify_all();});
  {std::unique_lock<std::mutex> g(state);fast=changed.wait_for(g,std::chrono::seconds(1),[&]{return other_done;});release_send=true;changed.notify_all();}
  sender.join();reopener.join();other.join();
  pool.close("other",2);pool.close("fixture",1);pool.close("fixture",1);
  const bool bad=!fast||!other_done||!pool.empty()||wrong_unlock||lock_error||wrong_context;
  std::cout<<"other_open_fast="<<fast<<" checks_passed="<<!bad<<std::endl;return bad?1:0;
 }
 if(argc==2 && std::string(argv[1])=="exception") {
  throw_send=true;try {pool.send("fixture",1,messages);return 2;}catch(const std::runtime_error&){}
  // Had the throwing send left the connection locked, this open's relock records lock_error.
  if(!pool.open("fixture",1,1) || pool.refs()!=2)return 3;
  pool.close("fixture",1);pool.close("fixture",1);
  if(!pool.empty()||wrong_context||wrong_unlock||lock_error)return 4;
  std::cout<<"PASS exception"<<std::endl;return 0;
 }
 int result=-99;std::thread sender([&]{result=pool.send("fixture",1,messages);});
 {std::unique_lock<std::mutex> g(state);if(!changed.wait_for(g,std::chrono::seconds(3),[]{return sending;}))std::abort();}
 std::thread reopener([&]{opener=true;bool success=pool.open("fixture",1,1);{std::lock_guard<std::mutex> g(state);reopened=success;changed.notify_all();}});
 {std::unique_lock<std::mutex> g(state);if(!changed.wait_for(g,std::chrono::seconds(3),[]{return reopen_event;}))std::abort();if(unsafe_open && !changed.wait_for(g,std::chrono::seconds(3),[]{return reopened;}))std::abort();release_send=true;changed.notify_all();}
 sender.join();reopener.join();bool bad=unsafe_open||wrong_unlock||wrong_context;
 if(result!=CONN_TRANSIENT || pool.refs()!=2)bad=true;
 pool.close("fixture",1);if(pool.refs()!=1)bad=true;pool.close("fixture",1);if(!pool.empty()||wrong_unlock||lock_error)bad=true;
 std::cout<<"unsafe_isOpen="<<unsafe_open<<" wrong_unlock="<<wrong_unlock<<" lock_error="<<lock_error<<" checks_passed="<<!bad<<std::endl;return bad?1:0;
}
