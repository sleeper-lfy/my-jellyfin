package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Read-only status of jobs executing on the connected computer. */
final class TaskCenter {
    private static final String[] STATES={"all","active","pending","failed","history"};
    private final Activity activity;
    private final Api api;
    private final long workId;
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private final LinearLayout rows;
    private final TextView status;
    private final Spinner category;
    private final Button refresh,previous,next;
    private final AlertDialog dialog;
    private int selection=0,offset=0,total=0;
    private boolean busy=false,closed=false;

    static AlertDialog show(Activity activity,Api api){return show(activity,api,0);}
    static AlertDialog show(Activity activity,Api api,long workId){
        if(activity.isFinishing()||activity.isDestroyed())return null;
        return new TaskCenter(activity,api,Math.max(0,workId)).dialog;
    }
    private int dp(int value){return MediaStyle.dp(activity,value);}
    private TextView label(String value,int size,int color){
        TextView view=new TextView(activity);view.setText(value);view.setTextSize(size);view.setTextColor(color);
        view.setPadding(0,dp(5),0,dp(5));return view;
    }
    private Button button(String value,Runnable action){
        Button button=new Button(activity);button.setText(value);MediaStyle.button(button,false,false,false);
        button.setOnClickListener(v->action.run());return button;
    }
    private TaskCenter(Activity owner,Api connection,long filterWork){
        activity=owner;api=connection;workId=filterWork;
        LinearLayout page=new LinearLayout(activity);page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(16),dp(8),dp(16),dp(8));page.setBackgroundColor(0xff18181d);
        page.setTag("computerTaskCenter");
        page.addView(label(workId>0?"显示关联此影片的电脑任务；确认、重试与停止请到电脑处理。":"任务在电脑执行；确认、重试与停止请到电脑任务中心。",13,0xffb0b0bb));
        LinearLayout controls=new LinearLayout(activity);page.addView(controls);
        category=new Spinner(activity);category.setContentDescription("电脑任务分类");category.setTag("computerTaskCategory");
        category.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_spinner_dropdown_item,
                new String[]{"全部","进行中","待确认与重试","失败","历史"}));
        controls.addView(category,new LinearLayout.LayoutParams(0,dp(48),1));
        refresh=button("刷新",()->load());refresh.setTag("refreshComputerTasks");controls.addView(refresh);
        status=label("正在读取电脑任务…",13,0xffb0b0bb);status.setTag("computerTasksStatus");page.addView(status);
        ScrollView scroll=new ScrollView(activity);scroll.setFillViewport(true);
        rows=new LinearLayout(activity);rows.setOrientation(LinearLayout.VERTICAL);rows.setTag("computerTaskRows");scroll.addView(rows);
        page.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout paging=new LinearLayout(activity);page.addView(paging);
        previous=button("上一页",()->{offset=Math.max(0,offset-30);load();});previous.setTag("previousTaskPage");
        next=button("下一页",()->{offset+=30;load();});next.setTag("nextTaskPage");
        paging.addView(previous,new LinearLayout.LayoutParams(0,-2,1));paging.addView(next,new LinearLayout.LayoutParams(0,-2,1));
        dialog=new AlertDialog.Builder(activity).setTitle(workId>0?"此影片的电脑任务":"电脑任务中心")
                .setView(page).setNegativeButton("关闭",null).create();
        dialog.setOnDismissListener(d->close());
        page.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener(){
            @Override public void onViewAttachedToWindow(View view){}
            @Override public void onViewDetachedFromWindow(View view){close();}
        });
        category.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> parent){}
            public void onItemSelected(AdapterView<?> parent,View view,int position,long id){
                if(position!=selection){selection=position;offset=0;load();}
            }
        });
        dialog.show();
        if(dialog.getWindow()!=null){
            int height=activity.getResources().getDisplayMetrics().heightPixels;
            dialog.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT,Math.max(dp(180),height-dp(64)));
        }
        load();
    }
    private void close(){if(closed)return;closed=true;network.shutdownNow();}
    private boolean alive(){return !closed&&!activity.isFinishing()&&!activity.isDestroyed()&&dialog.isShowing();}
    private void setBusy(boolean value){
        busy=value;refresh.setEnabled(!value);category.setEnabled(!value);
        previous.setEnabled(!value&&offset>0);next.setEnabled(!value&&offset+30<total);
    }
    private void load(){
        if(!alive()||busy)return;
        setBusy(true);status.setText("正在读取电脑任务…");
        String path="/api/tasks?state="+STATES[selection]+"&offset="+offset+"&limit=30"+(workId>0?"&work_id="+workId:"");
        network.execute(()->{
            try{
                JSONObject result=api.get(path);
                activity.runOnUiThread(()->{if(!alive())return;render(result);setBusy(false);});
            }catch(Exception error){
                activity.runOnUiThread(()->{
                    if(!alive())return;setBusy(false);
                    String message=error.getMessage()==null?"连接失败":error.getMessage();
                    boolean unsupported=message.contains("返回 404")||message.contains("返回 405");
                    status.setText(unsupported?"电脑端暂不支持任务列表，请更新电脑端。":"读取失败，可点击刷新重试："+message);
                });
            }
        });
    }
    private void render(JSONObject result){
        rows.removeAllViews();JSONArray items=result.optJSONArray("items");total=result.optInt("total");
        if(items==null||items.length()==0){rows.addView(label("当前分类没有任务",16,0xffb0b0bb));status.setText("共 "+total+" 项任务");return;}
        status.setText("电脑执行 · 第 "+(offset+1)+"–"+(offset+items.length())+" 项，共 "+total+" 项");
        for(int i=0;i<items.length();i++){
            JSONObject task=items.optJSONObject(i);if(task==null)continue;
            LinearLayout card=new LinearLayout(activity);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(12),dp(6),dp(12),dp(8));
            card.setBackground(MediaStyle.surface(activity,0xff222228,0xff35353e,8));
            LinearLayout.LayoutParams space=new LinearLayout.LayoutParams(-1,-2);space.setMargins(0,0,0,dp(10));rows.addView(card,space);
            String title=task.optString("work_title","");if(title.equals("null"))title="";
            card.addView(label(title.isEmpty()?task.optString("label","后台任务"):title,17,Color.WHITE));
            card.addView(label(task.optString("label","后台任务")+" · "+task.optString("status_label","状态未知"),14,0xff8cdef5));
            JSONObject progress=task.optJSONObject("progress");
            if(progress!=null&&progress.optDouble("total")>0){
                double completed=progress.optDouble("completed"),total=progress.optDouble("total");
                ProgressBar bar=new ProgressBar(activity,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(100);
                bar.setProgress((int)Math.max(0,Math.min(100,completed/total*100)));bar.setContentDescription("任务进度 "+bar.getProgress()+"%");card.addView(bar);
                String amount=progress.optString("unit").equals("bytes")?String.format(java.util.Locale.ROOT,"%.1f / %.1f MiB",completed/1048576,total/1048576):String.format(java.util.Locale.ROOT,"%.0f / %.0f",completed,total);
                card.addView(label("进度 "+amount,13,0xffb0b0bb));
            }
            if(!task.optString("stage").isEmpty())card.addView(label(task.optString("stage"),13,0xffb0b0bb));
            if(!task.optString("reason").isEmpty())card.addView(label(task.optString("reason"),14,0xffd6d6df));
            String updated=task.optString("updated");
            try{updated=OffsetDateTime.parse(updated).atZoneSameInstant(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("MM-dd HH:mm"));}catch(Exception ignored){updated="";}
            if(!updated.isEmpty())card.addView(label("更新于 "+updated,12,0xff9999a5));
        }
    }
}
