package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Bitmap;
import android.content.res.ColorStateList;
import android.util.LruCache;
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
import android.widget.ImageView;
import android.widget.HorizontalScrollView;
import com.google.android.material.card.MaterialCardView;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import com.google.android.material.progressindicator.LinearProgressIndicator;
import net.lumen.media.ui.theme.NativeActionTokens;
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
    private final ChipGroup category;
    private final Button refresh,previous,next;
    private final AlertDialog dialog;
    private final ImageRequests images=new ImageRequests(new LruCache<String,Bitmap>(4));
    private int selection=0,offset=0,total=0;
    private boolean busy=false,closed=false;

    static AlertDialog show(Activity activity,Api api){return show(activity,api,0);}
    static AlertDialog show(Activity activity,Api api,long workId){
        if(activity.isFinishing()||activity.isDestroyed())return null;
        return new TaskCenter(activity,api,Math.max(0,workId)).dialog;
    }
    private int dp(int value){return MediaStyle.dp(activity,value);}
    private Button button(String value,Runnable action){
        Button button=MediaStyle.action(activity);button.setText(value);MediaStyle.button(button,false,false,false);
        button.setOnClickListener(v->action.run());return button;
    }
    private TaskCenter(Activity owner,Api connection,long filterWork){
        activity=owner;api=connection;workId=filterWork;
        LinearLayout page=BiliAuxiliaryUi.column(activity);
        page.setPadding(dp(16),dp(8),dp(16),dp(16));page.setBackgroundColor(NativeActionTokens.background(true));
        page.setTag("computerTaskCenter");
        TextView readOnly=BiliAuxiliaryUi.supporting(activity,activity.getString(workId>0?R.string.bili_aux_tasks_related_read_only:R.string.bili_aux_tasks_read_only));readOnly.setContentDescription(activity.getString(R.string.bili_aux_tasks_read_only_description)+"。"+readOnly.getText());page.addView(readOnly);
        category=new ChipGroup(BiliAuxiliaryUi.themed(activity));category.setSingleLine(true);category.setSingleSelection(true);category.setSelectionRequired(true);category.setChipSpacingHorizontal(dp(8));category.setContentDescription("电脑任务分类");category.setTag("computerTaskCategory");
        String[] names={"全部","进行中",activity.getString(R.string.bili_aux_task_pending),"失败","历史"};
        for(int i=0;i<names.length;i++){
            Chip chip=new Chip(BiliAuxiliaryUi.themed(activity));chip.setId(View.generateViewId());chip.setTag("taskCategory:"+STATES[i]);chip.setText(names[i]);chip.setCheckable(true);chip.setEnsureMinTouchTargetSize(true);chip.setChipMinHeight(dp(32));chip.setTextSize(NativeActionTokens.supportingSp());chip.setChipStrokeWidth(dp(1));chip.setChipStrokeColor(ColorStateList.valueOf(NativeActionTokens.outlineVariant(true)));chip.setTextColor(new ColorStateList(new int[][]{{android.R.attr.state_checked},{}},new int[]{NativeActionTokens.primary(true),NativeActionTokens.onSurfaceVariant(true)}));chip.setChipBackgroundColor(new ColorStateList(new int[][]{{android.R.attr.state_checked},{}},new int[]{NativeActionTokens.container(true,0,true),NativeActionTokens.surfaceContainer(true)}));category.addView(chip);if(i==0)chip.setChecked(true);
        }
        HorizontalScrollView categories=new HorizontalScrollView(activity);categories.setHorizontalScrollBarEnabled(false);categories.addView(category);BiliAuxiliaryUi.add(page,categories,12);
        refresh=button("刷新",()->load());refresh.setTag("refreshComputerTasks");MediaStyle.quiet(refresh,"more","刷新电脑任务");((com.google.android.material.button.MaterialButton)refresh).setIconResource(R.drawable.bili_aux_refresh);
        LinearLayout heading=BiliAuxiliaryUi.header(activity,workId>0?"此影片的电脑任务":"电脑任务中心",this::dismiss);heading.addView(refresh,new LinearLayout.LayoutParams(dp(48),dp(48)));
        status=BiliAuxiliaryUi.supporting(activity,"正在读取电脑任务…");status.setTag("computerTasksStatus");status.setPadding(0,dp(8),0,dp(8));page.addView(status);
        ScrollView scroll=new ScrollView(activity);scroll.setFillViewport(true);
        rows=MediaStyle.actionColumn(activity);rows.setTag("computerTaskRows");scroll.addView(rows);
        page.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout paging=MediaStyle.actionRow(activity);paging.setTag("computerTaskPaging");LinearLayout.LayoutParams pagingGroup=new LinearLayout.LayoutParams(-1,-2);pagingGroup.topMargin=dp(16);page.addView(paging,pagingGroup);
        previous=button("上一页",()->{offset=Math.max(0,offset-30);load();});previous.setTag("previousTaskPage");
        next=button("下一页",()->{offset+=30;load();});next.setTag("nextTaskPage");
        paging.addView(previous,new LinearLayout.LayoutParams(0,-2,1));paging.addView(next,new LinearLayout.LayoutParams(0,-2,1));
        dialog=new AlertDialog.Builder(activity).setCustomTitle(heading)
                .setView(page).setNegativeButton("关闭",null).create();
        dialog.setOnDismissListener(d->close());
        page.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener(){
            @Override public void onViewAttachedToWindow(View view){}
            @Override public void onViewDetachedFromWindow(View view){close();}
        });
        category.setOnCheckedStateChangeListener((group,ids)->{if(ids.isEmpty())return;for(int index=0;index<group.getChildCount();index++){if(group.getChildAt(index).getId()==ids.get(0)&&index!=selection){selection=index;offset=0;load();break;}}});
        dialog.show();MediaStyle.sheet(dialog);
        if(dialog.getWindow()!=null){
            int height=activity.getResources().getDisplayMetrics().heightPixels;
            dialog.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT,Math.max(dp(180),height-dp(64)));
        }
        load();
    }
    private void dismiss(){dialog.dismiss();}
    private void close(){if(closed)return;closed=true;images.close();network.shutdownNow();}
    private boolean alive(){return !closed&&!activity.isFinishing()&&!activity.isDestroyed()&&dialog.isShowing();}
    private void setBusy(boolean value){
        busy=value;refresh.setEnabled(!value);category.setEnabled(!value);for(int index=0;index<category.getChildCount();index++)category.getChildAt(index).setEnabled(!value);
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
        images.cancelPage();rows.removeAllViews();JSONArray items=result.optJSONArray("items");total=result.optInt("total");
        if(items==null||items.length()==0){rows.addView(BiliAuxiliaryUi.body(activity,"当前分类没有任务"));status.setText("共 "+total+" 项任务");return;}
        status.setText("电脑执行 · 第 "+(offset+1)+"–"+(offset+items.length())+" 项，共 "+total+" 项");
        for(int i=0;i<items.length();i++){
            JSONObject task=items.optJSONObject(i);if(task==null)continue;
            MaterialCardView shell=BiliAuxiliaryUi.card(activity,"computerTaskCard:"+task.optString("id"));LinearLayout card=BiliAuxiliaryUi.cardContent(shell,12);rows.addView(shell,new LinearLayout.LayoutParams(-1,-2));
            String title=task.optString("work_title","");if(title.equals("null"))title="";
            LinearLayout summary=BiliAuxiliaryUi.row(activity);ImageView artwork=new ImageView(activity);artwork.setScaleType(ImageView.ScaleType.CENTER_CROP);artwork.setImageDrawable(new MediaStyle.ArtworkPlaceholder());artwork.setContentDescription(activity.getString(R.string.bili_aux_task_poster,title));summary.addView(artwork,new LinearLayout.LayoutParams(dp(64),dp(84)));long work=task.optLong("work_id",0);if(work>0)images.load(api,artwork,"/api/works/"+work+"/cover");
            LinearLayout description=BiliAuxiliaryUi.column(activity);description.setPadding(dp(12),0,0,0);TextView taskName=BiliAuxiliaryUi.body(activity,task.optString("label",activity.getString(R.string.bili_aux_task_background)));taskName.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);description.addView(taskName);
            TextView workTitle=BiliAuxiliaryUi.supporting(activity,title);workTitle.setMaxLines(2);workTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);workTitle.setPadding(0,dp(6),0,dp(6));if(!title.isEmpty())description.addView(workTitle);
            TextView state=BiliAuxiliaryUi.supporting(activity,task.optString("status_label",activity.getString(R.string.bili_aux_task_unknown)));state.setTextColor(NativeActionTokens.primary(true));state.setTag("computerTaskState:"+task.optString("id"));description.addView(state);summary.addView(description,new LinearLayout.LayoutParams(0,-2,1));card.addView(summary);
            JSONObject progress=task.optJSONObject("progress");
            if(progress!=null&&progress.optDouble("total")>0){
                double completed=progress.optDouble("completed"),total=progress.optDouble("total");
                LinearProgressIndicator bar=new LinearProgressIndicator(BiliAuxiliaryUi.themed(activity));bar.setIndicatorColor(NativeActionTokens.primary(true));bar.setTrackColor(NativeActionTokens.outlineVariant(true));bar.setMax(100);
                bar.setProgress((int)Math.max(0,Math.min(100,completed/total*100)));bar.setContentDescription("任务进度 "+bar.getProgress()+"%");LinearLayout.LayoutParams progressSpace=new LinearLayout.LayoutParams(-1,dp(4));progressSpace.topMargin=dp(12);progressSpace.bottomMargin=dp(8);card.addView(bar,progressSpace);
                String amount=progress.optString("unit").equals("bytes")?String.format(java.util.Locale.ROOT,"%.1f / %.1f MiB",completed/1048576,total/1048576):String.format(java.util.Locale.ROOT,"%.0f / %.0f",completed,total);
                card.addView(BiliAuxiliaryUi.supporting(activity,"进度 "+amount));
            }
            if(!task.optString("stage").isEmpty())BiliAuxiliaryUi.add(card,BiliAuxiliaryUi.supporting(activity,task.optString("stage")),8);
            if(!task.optString("reason").isEmpty())BiliAuxiliaryUi.add(card,BiliAuxiliaryUi.supporting(activity,task.optString("reason")),8);
            String updated=task.optString("updated");
            try{updated=OffsetDateTime.parse(updated).atZoneSameInstant(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("MM-dd HH:mm"));}catch(Exception ignored){updated="";}
            if(!updated.isEmpty())BiliAuxiliaryUi.add(card,BiliAuxiliaryUi.supporting(activity,"更新于 "+updated),8);
        }
    }
}
