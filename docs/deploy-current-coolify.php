<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$parent=App\Models\Service::whereUuid('tkt30aojscyme1bqu7n0ybbv')->firstOrFail();
$service=App\Models\Service::where('environment_id',$parent->environment_id)->where('name','table')->first();
if(!$service){
    $service=new App\Models\Service;
    $service->name='table';
    $service->description='Table: app-owned cookbook, weekly plans and approved Chronodrive shopping.';
    $service->environment_id=$parent->environment_id;
    $service->server_id=$parent->server_id;
    $service->destination_id=$parent->destination_id;
    $service->destination_type=$parent->destination_type;
}
$service->docker_compose_raw=file_get_contents('/tmp/table-compose.yaml');
validateDockerComposeForInjection($service->docker_compose_raw);
$service->save();
$service->parse(isNew:true);
$env=[];
foreach(file('/tmp/table-runtime.env',FILE_IGNORE_NEW_LINES|FILE_SKIP_EMPTY_LINES) as $line){[$k,$v]=explode('=',$line,2);$env[$k]=$v;}
foreach(['API_SERVER_KEY','TABLE_PASSWORD'] as $key){
    $service->environment_variables()->updateOrCreate(['resourceable_type'=>App\Models\Service::class,'resourceable_id'=>$service->id,'key'=>$key,'is_preview'=>false],['value'=>$env[$key]]);
}
$application=$service->applications()->where('name','table')->firstOrFail();
$application->fqdn='https://table.vermeille.fr:8080';
$application->save();
updateCompose($application);
$service->refresh();
$service->parse();
$activity=App\Actions\Service\StartService::run($service);
echo json_encode(['service_uuid'=>$service->uuid,'activity_id'=>$activity->id,'url'=>'https://table.vermeille.fr']),"\n";
unlink('/tmp/table-runtime.env');
