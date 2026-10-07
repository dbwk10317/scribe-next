// Pthread failure injection for actual StoreQueue construction; no daemon/socket.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "common.h"
#include "store_queue.h"
#include <set>
#include <system_error>
#include <iostream>
void fixture_configure(){}
std::string fixture_status(){return "";}
static int fail_step=0,calls=0,bad_destroy=0,bad_join=0,joins=0;
static bool started=false;
static std::set<void*> live;
extern "C" int __real_pthread_mutex_init(pthread_mutex_t*,const pthread_mutexattr_t*);
extern "C" int __real_pthread_mutex_destroy(pthread_mutex_t*);
extern "C" int __real_pthread_cond_init(pthread_cond_t*,const pthread_condattr_t*);
extern "C" int __real_pthread_cond_destroy(pthread_cond_t*);
extern "C" int __real_pthread_create(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);
extern "C" int __real_pthread_join(pthread_t,void**);
extern "C" int __wrap_pthread_mutex_init(pthread_mutex_t* p,const pthread_mutexattr_t* a){if(++calls==fail_step)return EAGAIN;int r=__real_pthread_mutex_init(p,a);if(!r)live.insert(p);return r;}
extern "C" int __wrap_pthread_cond_init(pthread_cond_t* p,const pthread_condattr_t* a){if(++calls==fail_step)return EAGAIN;int r=__real_pthread_cond_init(p,a);if(!r)live.insert(p);return r;}
extern "C" int __wrap_pthread_mutex_destroy(pthread_mutex_t* p){if(!live.erase(p)){++bad_destroy;return EINVAL;}return __real_pthread_mutex_destroy(p);}
extern "C" int __wrap_pthread_cond_destroy(pthread_cond_t* p){if(!live.erase(p)){++bad_destroy;return EINVAL;}return __real_pthread_cond_destroy(p);}
extern "C" int __wrap_pthread_create(pthread_t* t,const pthread_attr_t* a,void*(*f)(void*),void* p){++calls;if(fail_step)return EAGAIN;int r=__real_pthread_create(t,a,f,p);started=!r;return r;}
extern "C" int __wrap_pthread_join(pthread_t t,void** p){++joins;if(!started){++bad_join;return ESRCH;}return __real_pthread_join(t,p);}
static bool check(int step){
 fail_step=step;calls=bad_destroy=bad_join=joins=0;started=false;bool rejected=false;
 ScribeContext context;
 try {StoreQueue queue(context,"fixture","fixture",1);if(step==0||step==5)queue.stop();}
 catch(const std::system_error& error){rejected=error.code().value()==EAGAIN;}
 bool ok=live.empty()&&!bad_destroy&&!bad_join&&(step?rejected:started&&joins==1);
 std::cout<<"step="<<step<<" rejected="<<rejected<<" live="<<live.size()<<" bad_destroy="<<bad_destroy<<" bad_join="<<bad_join<<std::endl;return ok;
}
int main(int argc,char**argv){if(argc==2)return check(std::atoi(argv[1]))?0:1;for(int n=0;n<=5;++n)if(!check(n))return 1;std::cout<<"PASS init failure matrix"<<std::endl;}
